"""API de Rumbo AI (FastAPI)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .agent import Agent, AnthropicProvider, DemoProvider, ModelProvider, RunStats, ToolContext
from .agent.tools import destinations
from .config import get_settings
from .db import AgentRun, SessionLocal, Trip, get_db, init_db
from .sessions import build_session_store

settings = get_settings()
DbSession = Annotated[Session, Depends(get_db)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Rumbo AI",
    version="1.0.0",
    lifespan=lifespan,
    description="Agente de IA que planifica viajes con un loop agéntico propio.",
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"], allow_headers=["*"])


def build_provider() -> ModelProvider:
    if settings.use_demo:
        return DemoProvider(delay_s=settings.demo_delay_ms / 1000)
    return AnthropicProvider(settings.anthropic_api_key, settings.agent_model, settings.agent_effort)


provider = build_provider()
agent = Agent(provider, max_iterations=settings.agent_max_iterations)

# Historial por sesión: en memoria en local, en Redis cuando hay varias réplicas.
sessions = build_session_store(settings.redis_url)


def trip_to_dict(t: Trip) -> dict:
    return {
        "id": t.id,
        "created_at": t.created_at.isoformat(),
        "title": t.title,
        "destination_id": t.destination_id,
        "destination_name": t.destination_name,
        "flag": t.flag,
        "month": t.month,
        "days": t.days,
        "travelers": t.travelers,
        "style": t.style,
        "summary": t.summary,
        "climate": t.climate,
        "budget": t.budget,
        "itinerary": t.itinerary,
    }


def _save_trip(data: dict) -> dict:
    with SessionLocal() as db:
        trip = Trip(**data)
        db.add(trip)
        db.commit()
        return trip_to_dict(trip)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    session_id: str | None = None


@app.get("/api/health")
def health() -> dict:
    """Liveness: el proceso responde."""
    return {"status": "ok", "mode": provider.name, "model": provider.model}


@app.get("/api/ready")
def ready() -> JSONResponse:
    """Readiness: la base de datos y Redis están disponibles. Kubernetes no envía tráfico hasta que responde 200."""
    checks: dict[str, str] = {}
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:  # noqa: BLE001
        checks["database"] = f"error: {type(e).__name__}"
    try:
        checks["sessions"] = "ok" if sessions.ping() else "error"
    except Exception as e:  # noqa: BLE001
        checks["sessions"] = f"error: {type(e).__name__}"
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse({"status": "ready" if ok else "not_ready", "checks": checks}, status_code=200 if ok else 503)


@app.get("/api/destinations")
def list_destinations() -> list[dict]:
    return [{k: d[k] for k in ("id", "name", "country", "flag", "description", "tags")} for d in destinations().values()]


@app.post("/api/chat")
def chat(req: ChatRequest) -> StreamingResponse:
    session_id = req.session_id or str(uuid.uuid4())
    lock = sessions.lock(session_id)

    def stream() -> Iterator[str]:
        if not lock.acquire(blocking=False):
            yield _sse({"type": "error", "message": "Ya hay una petición en curso en esta sesión."})
            return
        history = sessions.get(session_id)
        run_id = str(uuid.uuid4())
        stats = RunStats()
        ctx = ToolContext(save_trip=_save_trip)
        try:
            yield _sse(
                {
                    "type": "run_started",
                    "run_id": run_id,
                    "session_id": session_id,
                    "mode": provider.name,
                    "model": provider.model,
                }
            )
            for event in agent.run(history, req.message, ctx, stats):
                yield _sse(event)
                if event["type"] == "tool_result" and event["name"] == "save_trip" and not event["is_error"]:
                    yield _sse({"type": "trip", "trip": ctx.saved[-1]})
            if stats.status == "completed":
                sessions.save(session_id, history)
            yield _sse(
                {
                    "type": "done",
                    "stats": {
                        "iterations": stats.iterations,
                        "tool_calls": stats.tool_calls,
                        "tool_errors": stats.tool_errors,
                        "input_tokens": stats.input_tokens,
                        "output_tokens": stats.output_tokens,
                        "duration_ms": stats.duration_ms,
                        "status": stats.status,
                    },
                }
            )
        finally:
            lock.release()
            with SessionLocal() as db:
                db.add(
                    AgentRun(
                        id=run_id,
                        session_id=session_id,
                        prompt=req.message,
                        mode=provider.name,
                        model=provider.model,
                        status=stats.status,
                        iterations=stats.iterations,
                        tool_calls=stats.tool_calls,
                        tool_errors=stats.tool_errors,
                        input_tokens=stats.input_tokens,
                        output_tokens=stats.output_tokens,
                        duration_ms=stats.duration_ms,
                        trip_id=ctx.saved[-1]["id"] if ctx.saved else None,
                    )
                )
                db.commit()

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@app.post("/api/sessions/{session_id}/reset")
def reset_session(session_id: str) -> dict:
    sessions.reset(session_id)
    return {"status": "reset"}


@app.get("/api/trips")
def list_trips(db: DbSession) -> list[dict]:
    trips = db.scalars(select(Trip).order_by(Trip.created_at.desc()).limit(50))
    return [trip_to_dict(t) for t in trips]


@app.get("/api/trips/{trip_id}")
def get_trip(trip_id: int, db: DbSession) -> dict:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(404, "Viaje no encontrado")
    return trip_to_dict(trip)


@app.delete("/api/trips/{trip_id}", status_code=204)
def delete_trip(trip_id: int, db: DbSession) -> None:
    trip = db.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(404, "Viaje no encontrado")
    db.delete(trip)
    db.commit()


@app.get("/api/stats")
def stats(db: DbSession) -> dict:
    row = db.execute(
        select(
            func.count(AgentRun.id),
            func.avg(AgentRun.duration_ms),
            func.sum(AgentRun.tool_calls),
            func.sum(AgentRun.tool_errors),
            func.sum(AgentRun.input_tokens + AgentRun.output_tokens),
            func.avg(AgentRun.iterations),
        )
    ).one()
    runs, avg_ms, calls, errors, tokens, avg_iter = row
    completed = db.scalar(select(func.count(AgentRun.id)).where(AgentRun.status == "completed")) or 0
    return {
        "runs": runs or 0,
        "success_rate": round(completed / runs, 3) if runs else None,
        "avg_duration_ms": round(avg_ms or 0),
        "avg_iterations": round(avg_iter or 0, 1),
        "tool_calls": calls or 0,
        "tool_errors": errors or 0,
        "tokens": tokens or 0,
        "trips": db.scalar(select(func.count(Trip.id))) or 0,
    }
