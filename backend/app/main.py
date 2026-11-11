"""API de Rumbo AI (FastAPI)."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .agent import (
    Agent,
    AnthropicProvider,
    DemoProvider,
    GuardedProvider,
    ModelProvider,
    OpenAICompatibleProvider,
    RunStats,
    ToolContext,
)
from .agent.tools import destinations
from .config import get_settings
from .db import AgentRun, SessionLocal, Trip, get_db, init_db
from .limits import LimitsConfig, build_limits, client_ip
from .rag import get_rag
from .sessions import build_session_store

settings = get_settings()
log = logging.getLogger("rumbo")
DbSession = Annotated[Session, Depends(get_db)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    try:
        # Indexa las guías al arrancar (incremental: solo lo nuevo o modificado).
        get_rag()
    except Exception:  # noqa: BLE001 - la API arranca igual; la herramienta reintentará al usarse
        log.exception("No se pudo inicializar el RAG")
    yield


app = FastAPI(
    title="Rumbo AI",
    version="1.0.0",
    lifespan=lifespan,
    description="Agente de IA que planifica viajes con un loop agéntico propio.",
)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_list, allow_methods=["*"], allow_headers=["*"])


def build_real_providers() -> list[ModelProvider]:
    """Cadena de modelos reales configurados, en orden de prioridad. Vacía: modo demo."""
    chain: list[ModelProvider] = []
    for name in settings.llm_chain:
        if name == "claude":
            chain.append(AnthropicProvider(settings.anthropic_api_key, settings.agent_model, settings.agent_effort))
        elif name == "gemini":
            chain.append(
                OpenAICompatibleProvider(
                    settings.gemini_api_key,
                    settings.gemini_model,
                    settings.gemini_base_url,
                    name="gemini",
                    max_tokens=settings.llm_max_output_tokens,
                )
            )
        elif name == "groq":
            chain.append(
                OpenAICompatibleProvider(
                    settings.groq_api_key,
                    settings.groq_model,
                    settings.groq_base_url,
                    max_tokens=settings.llm_max_output_tokens,
                )
            )
        elif name == "extra":
            chain.append(
                OpenAICompatibleProvider(
                    settings.extra_llm_api_key,
                    settings.extra_llm_model,
                    settings.extra_llm_base_url,
                    name=settings.extra_llm_name,
                    max_tokens=settings.llm_max_output_tokens,
                )
            )
    return chain


real_providers = build_real_providers()
demo_provider = DemoProvider(delay_s=settings.demo_delay_ms / 1000)
# Para /api/health: el proveedor principal de esta instancia.
provider: ModelProvider = real_providers[0] if real_providers else demo_provider

# Historial por sesión: en memoria en local, en Redis cuando hay varias réplicas.
sessions = build_session_store(settings.redis_url)
# Límites de uso y presupuesto del modelo real (compartidos en Redis si hay varias réplicas).
limits = build_limits(
    settings.redis_url,
    LimitsConfig(
        flood_per_minute=settings.rate_limit_flood_per_minute,
        llm_per_hour=settings.rate_limit_llm_per_hour,
        llm_per_day=settings.rate_limit_llm_per_day,
        daily_token_budget=settings.llm_daily_token_budget,
        min_tokens_per_run=settings.llm_min_tokens_per_run,
    ),
)


def available_providers() -> list[ModelProvider]:
    """Proveedores de la cadena que no están en pausa por cuota o por no responder."""
    return [p for p in real_providers if not limits.cooling_down(p.name)]


def provider_for_run(ip: str) -> tuple[ModelProvider, str | None]:
    """Decide qué modelo atiende esta petición y, si es el demo por un límite, por qué."""
    if not real_providers:
        return demo_provider, None
    chain = available_providers()
    if not limits.can_start_run():
        return demo_provider, "Hoy se ha agotado el presupuesto de IA real de Rumbo: respondo en modo demo."
    if not chain:
        return demo_provider, "Los modelos gratuitos de Rumbo han agotado su cuota por ahora: respondo en modo demo."
    if not limits.take_ip_quota(ip):
        return demo_provider, (
            f"Has usado tus consultas con IA real ({limits.config.llm_per_hour} por hora, "
            f"{limits.config.llm_per_day} al día): respondo en modo demo."
        )
    return GuardedProvider(chain, demo_provider, limits), None


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
    # "real": el modelo configurado (si hay cupo); "demo": fuerza el modo demo, sin gastar cupo ni tokens.
    mode: Literal["real", "demo"] = "real"


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


@app.get("/api/rag/status")
def rag_status() -> dict:
    """Qué embedder y qué almacén de vectores se están usando, y cuántos fragmentos hay indexados."""
    return get_rag().status()


@app.get("/api/rag/search")
def rag_search(
    q: Annotated[str, Query(min_length=3, max_length=300)],
    destination_id: str | None = None,
    k: Annotated[int, Query(ge=1, le=10)] = 4,
) -> dict:
    """La misma búsqueda que usa el agente, expuesta para depurar y enseñar el RAG."""
    if destination_id and destination_id not in destinations():
        raise HTTPException(404, "Destino desconocido")
    result = get_rag().retriever.search(q, k=k, destination_id=destination_id)
    return {
        "query": q,
        "destination_id": result.destination_id,
        "retrieval": result.mode,
        "expanded_terms": result.expanded_terms,
        "timings_ms": result.timings_ms,
        "results": [h.to_dict() for h in result.hits],
    }


@app.get("/api/usage")
def usage(request: Request) -> dict:
    """Modo con el que se responderá a quien pregunta y cuántas consultas con IA real le quedan."""
    ip = client_ip(request.headers, request.client.host if request.client else None)
    if not real_providers:
        return {"mode": "demo", "model": demo_provider.model, "real_ai": False}
    mine = limits.ip_remaining(ip)
    chain = available_providers()
    # El primero disponible es el que atenderá la próxima consulta.
    current = chain[0] if chain else real_providers[0]
    return {
        "mode": current.name,
        "model": current.model,
        "chain": [p.name for p in real_providers],
        "real_ai": bool(chain) and limits.can_start_run() and min(mine.values()) > 0,
        "remaining": mine,
        **limits.status(),
    }


@app.post("/api/chat", response_model=None)
def chat(req: ChatRequest, request: Request) -> StreamingResponse | JSONResponse:
    ip = client_ip(request.headers, request.client.host if request.client else None)
    if not limits.allow_request(ip):
        return JSONResponse(
            {"detail": "Demasiadas peticiones seguidas. Espera un minuto."}, status_code=429, headers={"Retry-After": "60"}
        )
    session_id = req.session_id or str(uuid.uuid4())
    lock = sessions.lock(session_id)
    run_provider, notice = (demo_provider, None) if req.mode == "demo" else provider_for_run(ip)
    agent = Agent(run_provider, max_iterations=settings.agent_max_iterations)

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
                    "mode": run_provider.name,
                    "model": run_provider.model,
                }
            )
            if notice:
                yield _sse({"type": "notice", "text": notice})
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
                        mode=run_provider.name,
                        model=run_provider.model,
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
