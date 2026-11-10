"""Herramientas del agente de viajes.

Cada herramienta se define una sola vez con un modelo Pydantic: de él sale el
esquema JSON que ve el modelo y la validación de los argumentos que llegan.
Si la validación falla, el error vuelve al modelo como `is_error` y él se corrige.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "destinations.json"

Style = Literal["mochilero", "confort", "lujo"]
Interest = Literal[
    "gastronomia",
    "historia",
    "arte",
    "nocturna",
    "playa",
    "naturaleza",
    "aventura",
    "fotografia",
    "diseno",
    "tecnologia",
    "compras",
]
MONTHS = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


class ToolError(Exception):
    """Error que se devuelve al modelo para que corrija su siguiente paso."""


@lru_cache
def destinations() -> dict[str, dict]:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return {d["id"]: d for d in data}


def _get_destination(destination_id: str) -> dict:
    dest = destinations().get(destination_id)
    if dest is None:
        valid = ", ".join(sorted(destinations()))
        raise ToolError(f"Destino '{destination_id}' desconocido. Ids válidos: {valid}")
    return dest


# --- Argumentos ---------------------------------------------------------------


class SearchDestinationsArgs(BaseModel):
    interests: list[Interest] = Field(default_factory=list, description="Intereses del viajero")
    month: int | None = Field(None, ge=1, le=12, description="Mes del viaje (1-12), si se conoce")
    style: Style = Field("confort", description="Estilo de viaje")
    max_daily_budget_eur: float | None = Field(None, gt=0, description="Presupuesto máximo por persona y día")


class ClimateArgs(BaseModel):
    destination_id: str = Field(description="Id del destino, por ejemplo 'kioto'")
    month: int = Field(ge=1, le=12)


class BudgetArgs(BaseModel):
    destination_id: str
    days: int = Field(ge=1, le=30)
    travelers: int = Field(1, ge=1, le=12)
    style: Style = "confort"


class ItineraryArgs(BaseModel):
    destination_id: str
    days: int = Field(ge=1, le=14)
    interests: list[Interest] = Field(default_factory=list)


class SearchGuidesArgs(BaseModel):
    query: str = Field(min_length=3, max_length=300, description="Pregunta práctica del viajero, en sus palabras")
    destination_id: str | None = Field(None, description="Id del destino para filtrar, si la pregunta es de uno concreto")


class SaveTripArgs(BaseModel):
    title: str = Field(min_length=3, max_length=160, description="Título atractivo del viaje")
    destination_id: str
    days: int = Field(ge=1, le=14)
    travelers: int = Field(1, ge=1, le=12)
    style: Style = "confort"
    month: int | None = Field(None, ge=1, le=12)
    interests: list[Interest] = Field(default_factory=list)
    summary: str = Field(max_length=600, description="Resumen de 1-2 frases para el usuario")


# --- Implementaciones -----------------------------------------------------------


def search_destinations(args: SearchDestinationsArgs) -> dict:
    results = []
    for d in destinations().values():
        matched = [i for i in args.interests if i in d["tags"]]
        score = len(matched) * 2.0
        reasons = [f"encaja con {', '.join(matched)}"] if matched else []
        cost = d["daily_cost_eur"][args.style]
        if args.max_daily_budget_eur and cost > args.max_daily_budget_eur:
            continue
        if args.month:
            temp = d["climate"]["avg_temp_c"][args.month - 1]
            rain = d["climate"]["rain_days"][args.month - 1]
            if 16 <= temp <= 28:
                score += 1.5
                reasons.append(f"{temp} °C de media")
            if rain <= 6:
                score += 1.0
                reasons.append("pocos días de lluvia")
        results.append(
            {
                "destination_id": d["id"],
                "name": d["name"],
                "country": d["country"],
                "flag": d["flag"],
                "daily_cost_eur": cost,
                "score": round(score, 1),
                "why": "; ".join(reasons) or "opción versátil",
            }
        )
    if not results:
        raise ToolError("Ningún destino cumple el presupuesto. Prueba a subirlo o cambiar el estilo de viaje.")
    results.sort(key=lambda r: (-r["score"], r["daily_cost_eur"]))
    return {"results": results[:4]}


def get_climate(args: ClimateArgs) -> dict:
    d = _get_destination(args.destination_id)
    temp = d["climate"]["avg_temp_c"][args.month - 1]
    rain = d["climate"]["rain_days"][args.month - 1]
    if temp < 5:
        verdict = "frío: ropa de abrigo imprescindible"
    elif temp > 30:
        verdict = "mucho calor: planifica actividades a primera y última hora"
    elif rain >= 12:
        verdict = "lluvioso: reserva planes de interior"
    else:
        verdict = "buen momento para visitarlo"
    return {"destination": d["name"], "month": MONTHS[args.month - 1], "avg_temp_c": temp, "rain_days": rain, "verdict": verdict}


def estimate_budget(args: BudgetArgs) -> dict:
    d = _get_destination(args.destination_id)
    per_day = d["daily_cost_eur"][args.style]
    split = {"alojamiento": 0.45, "comida": 0.30, "transporte_local": 0.10, "actividades": 0.15}
    per_person = {k: round(per_day * v * args.days) for k, v in split.items()}
    total_person = sum(per_person.values())
    return {
        "destination": d["name"],
        "style": args.style,
        "days": args.days,
        "travelers": args.travelers,
        "per_person": per_person,
        "total_per_person_eur": total_person,
        "total_eur": total_person * args.travelers,
        "note": "Estimación orientativa sin vuelos.",
    }


def _time_of_day(poi: dict) -> float:
    name = poi["name"].lower()
    if "amanecer" in name:
        return 0
    if poi["duration_h"] >= 5:
        return 0.5  # excursiones largas: salir por la mañana
    if poi["category"] == "nocturna" or "cena" in name or "noche" in name:
        return 2
    if "atardecer" in name:
        return 1.5
    return 1


def build_itinerary(args: ItineraryArgs) -> dict:
    d = _get_destination(args.destination_id)
    # Primero lo que encaja con los intereses; las excursiones largas, al final.
    pois = sorted(d["pois"], key=lambda p: (p["category"] not in args.interests, p["duration_h"] > 6))
    per_day = min(3, max(1, math.ceil(len(pois) / args.days)))
    night = [p for p in pois if p["category"] == "nocturna"]
    rest = [p for p in pois if p["category"] != "nocturna"]
    days = []
    for n in range(args.days):
        # Como mucho un plan nocturno por día, para que siempre caiga por la noche.
        chunk = [night.pop(0)] if night and per_day > 1 else []
        while len(chunk) < per_day and (rest or night):
            pool = rest or night
            if chunk and sum(p["duration_h"] for p in chunk) + pool[0]["duration_h"] > 10:
                break  # no más de ~10 h de actividades al día
            chunk.append(pool.pop(0))
        if not chunk:
            days.append(
                {
                    "day": n + 1,
                    "activities": [
                        {
                            "slot": "día libre",
                            "name": f"Día libre para perderse por {d['name']} o repetir lo que más guste",
                            "category": "libre",
                            "duration_h": 0,
                            "price_eur": 0,
                            "area": "—",
                        }
                    ],
                }
            )
            continue
        # Orden natural dentro del día: amanecer primero, cenas y planes nocturnos al final.
        chunk.sort(key=_time_of_day)
        last = _time_of_day(chunk[-1])
        end = "noche" if last >= 2 else "atardecer" if last == 1.5 else "tarde"
        slots = {1: ["mañana"], 2: ["mañana", end], 3: ["mañana", "mediodía", end]}[len(chunk)]
        if len(chunk) == 1 and chunk[0]["duration_h"] > 6:
            slots = ["día completo"]
        days.append({"day": n + 1, "activities": [{"slot": sl, **p} for sl, p in zip(slots, chunk, strict=True)]})
    return {"destination": d["name"], "days": days}


def search_travel_guides(args: SearchGuidesArgs) -> dict:
    """RAG: recupera los fragmentos de las guías más relevantes para la pregunta."""
    from ..config import get_settings
    from ..rag import get_rag

    if args.destination_id:
        _get_destination(args.destination_id)
    result = get_rag().retriever.search(args.query, k=get_settings().rag_top_k, destination_id=args.destination_id)
    out = {
        "query": args.query,
        "destination_id": result.destination_id,
        "retrieval": result.mode,
        "expanded_terms": result.expanded_terms,
        "timings_ms": result.timings_ms,
        "results": [h.to_dict() for h in result.hits],
    }
    if result.hits:
        out["instructions"] = (
            "Responde solo con la información de estos fragmentos y cita la fuente como (Guía de <destino> · <sección>). "
            "Recuerda al usuario que verifique los requisitos oficiales de entrada antes de viajar."
        )
    else:
        out["instructions"] = "Las guías no cubren esta pregunta: dilo al usuario en lugar de inventar la respuesta."
    return out


# --- Registro -----------------------------------------------------------------


@dataclass
class ToolContext:
    """Dependencias que algunas herramientas necesitan (p. ej. guardar en BD)."""

    save_trip: Callable[[dict], dict] | None = None
    saved: list[dict] = field(default_factory=list)


def save_trip(args: SaveTripArgs, ctx: ToolContext) -> dict:
    d = _get_destination(args.destination_id)
    if ctx.save_trip is None:
        raise ToolError("Guardar viajes no está disponible en este entorno.")
    # El plan se recalcula en el servidor: no se confía en datos largos generados por el modelo.
    trip = {
        "title": args.title,
        "destination_id": d["id"],
        "destination_name": d["name"],
        "flag": d["flag"],
        "month": args.month,
        "days": args.days,
        "travelers": args.travelers,
        "style": args.style,
        "summary": args.summary,
        "climate": get_climate(ClimateArgs(destination_id=d["id"], month=args.month)) if args.month else None,
        "budget": estimate_budget(BudgetArgs(destination_id=d["id"], days=args.days, travelers=args.travelers, style=args.style)),
        "itinerary": build_itinerary(ItineraryArgs(destination_id=d["id"], days=args.days, interests=args.interests))["days"],
    }
    saved = ctx.save_trip(trip)
    ctx.saved.append(saved)
    return {"trip_id": saved["id"], "status": "guardado"}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[..., dict]
    needs_context: bool = False

    def schema(self) -> dict:
        schema = self.args_model.model_json_schema()
        schema.pop("title", None)
        return {"name": self.name, "description": self.description, "input_schema": schema}


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in [
        Tool(
            "search_destinations",
            "Busca y puntúa destinos según intereses, mes, estilo y presupuesto diario. "
            "Úsala si el usuario no ha decidido destino.",
            SearchDestinationsArgs,
            search_destinations,
        ),
        Tool("get_climate", "Clima medio de un destino en un mes concreto.", ClimateArgs, get_climate),
        Tool("estimate_budget", "Calcula el presupuesto estimado (sin vuelos) por persona y total.", BudgetArgs, estimate_budget),
        Tool(
            "build_itinerary",
            "Genera un itinerario día a día con actividades reales del destino.",
            ItineraryArgs,
            build_itinerary,
        ),
        Tool(
            "search_travel_guides",
            "Busca en las guías prácticas de los destinos (RAG): documentación y visados, dinero y propinas, "
            "transporte, seguridad, costumbres, enchufes, salud y dónde alojarse. Úsala para cualquier pregunta "
            "práctica en lugar de responder de memoria.",
            SearchGuidesArgs,
            search_travel_guides,
        ),
        Tool(
            "save_trip",
            "Guarda el viaje final para que el usuario lo vea en su panel. Llámala una sola vez, al final.",
            SaveTripArgs,
            save_trip,
            needs_context=True,
        ),
    ]
}


def tool_schemas() -> list[dict]:
    return [t.schema() for t in TOOLS.values()]


def execute_tool(name: str, raw_args: dict[str, Any], ctx: ToolContext | None = None) -> dict:
    tool = TOOLS.get(name)
    if tool is None:
        raise ToolError(f"Herramienta desconocida: {name}")
    try:
        args = tool.args_model.model_validate(raw_args)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors())
        raise ToolError(f"Argumentos no válidos para {name}: {problems}") from None
    if tool.needs_context:
        return tool.handler(args, ctx or ToolContext())
    return tool.handler(args)
