"""Proveedor de demostración: simula a Claude sin API key.

Interpreta la petición con reglas simples y decide qué herramientas llamar,
devolviendo la misma estructura que el proveedor real. Las herramientas se
ejecutan de verdad, así que la demo enseña el loop agéntico completo.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import dataclass, field

from ..rag.text import tokenize
from .providers import Block, ModelTurn
from .tools import MONTHS, destinations

ALIASES = {
    "lisboa": ["lisboa", "portugal"],
    "kioto": ["kioto", "kyoto", "japon"],
    "reikiavik": ["reikiavik", "islandia", "auroras"],
    "cdmx": ["ciudad de mexico", "cdmx", "mexico"],
    "marrakech": ["marrakech", "marruecos"],
    "copenhague": ["copenhague", "dinamarca"],
    "seul": ["seul", "corea"],
    "buenosaires": ["buenos aires", "argentina"],
    "ciudaddelcabo": ["ciudad del cabo", "sudafrica"],
    "nuevayork": ["nueva york", "new york", "manhattan"],
}
INTEREST_WORDS = {
    "gastronomia": ["comer", "comida", "gastronom", "restaurante", "tapas", "vino"],
    "historia": ["historia", "templo", "museo", "cultura", "monument"],
    "arte": ["arte", "museo", "diseño", "arquitectura"],
    "nocturna": ["noche", "fiesta", "bares", "copas", "nocturn"],
    "playa": ["playa", "mar", "sol"],
    "naturaleza": ["naturaleza", "montaña", "senderismo", "parque"],
    "aventura": ["aventura", "excursion", "adrenalina"],
    "fotografia": ["foto", "instagram"],
    "tecnologia": ["tecnolog", "futurista", "gadgets"],
    "compras": ["compras", "shopping", "tiendas"],
}


# Preguntas prácticas que se responden con las guías (RAG) en lugar de planificar un viaje.
PRACTICAL = re.compile(
    r"\b(visad\w*|visa|pasaporte|dni|papeleo|documentacion|requisitos|propinas?|moneda|efectivo|cajeros?|"
    r"tarjetas?|transporte|mover\w*|muevo|metro|taxis?|autobus\w*|aeropuerto|segur[oa]|seguridad|peligros\w*|robos?|"
    r"timos?|costumbres?|etiqueta|vestir|enchufes?|adaptador|voltaje|wifi|internet|grifo|vacunas?|salud|"
    r"alojar\w*|dormir|barrios?|consejos?)\b"
)
PLANNING = re.compile(
    r"\b(\d+\s*(dias|noches)|fin de semana|finde|una semana|planifica\w*|organiza\w*|itinerario|escapada|sorprendeme)\b"
)


# Señales de que el mensaje va de viajes (o es un ajuste del viaje en curso: "más barato", "mejor 2 días").
TRAVEL = re.compile(
    r"\b(viaj\w*|destino\w*|vacacion\w*|escapada|turis\w*|visitar|conocer|ir a|plan\w*|itinerario|ruta|"
    r"dias?|noches?|semana|finde|personas?|pareja|amigos|familia|viajeros?|presupuesto|barat\w*|economic\w*|"
    r"lujo|mochilero|confort|caro|precio|clima|tiempo|playa|montana|museos?|templos?|gastronomia|comer|comida|"
    r"historia|arte|naturaleza|aventura|fotografia|compras|tapas|fiesta|otro|cambia\w*|anade|quita\w*|mas|menos|"
    r"sorprendeme|si|vale|ok)\b"
)
OFF_TOPIC_REPLY = (
    "Solo puedo ayudarte con viajes: planificar una escapada o resolver dudas prácticas como visados, "
    'transporte o propinas. Prueba, por ejemplo, con "4 días en Lisboa en junio".'
)


def is_travel_related(text: str) -> bool:
    t = _norm(text)
    return bool(
        PRACTICAL.search(t)
        or PLANNING.search(t)
        or TRAVEL.search(t)
        or any(w in t for words in ALIASES.values() for w in words)
        or any(m in t for m in MONTHS)
    )


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


@dataclass
class Request:
    destination_id: str | None = None
    days: int = 4
    travelers: int = 1
    month: int | None = None
    style: str = "confort"
    interests: list[str] = field(default_factory=list)
    max_daily_budget_eur: float | None = None


def parse_request(texts: list[str]) -> Request:
    """Combina todos los mensajes del usuario; lo más reciente manda."""
    req = Request()
    for raw in texts:
        t = _norm(raw)
        matched = [d for d, words in ALIASES.items() if any(w in t for w in words)]
        if matched:
            req.destination_id = matched[-1]
        elif any(w in t for w in ["otro destino", "otro sitio", "mejor algo", "cambia de destino", "sorprendeme"]):
            req.destination_id = None
        if m := re.search(r"(\d+)\s*(dias|noches)", t):
            req.days = max(1, min(14, int(m.group(1))))
        elif "fin de semana" in t or "finde" in t:
            req.days = 3
        elif "una semana" in t:
            req.days = 7
        if m := re.search(r"(\d+)\s*(personas|viajeros|amigos|adultos)", t):
            req.travelers = max(1, min(12, int(m.group(1))))
        elif "pareja" in t:
            req.travelers = 2
        for i, name in enumerate(MONTHS, start=1):
            if name in t:
                req.month = i
        if any(w in t for w in ["lujo", "premium", "sin limite"]):
            req.style = "lujo"
        elif any(w in t for w in ["mochilero", "barato", "low cost", "economico", "ajustado"]):
            req.style = "mochilero"
        found = [k for k, words in INTEREST_WORDS.items() if any(w in t for w in words)]
        if found:
            req.interests = found
        if m := re.search(r"(\d+)\s*(€|eur|euros)\s*(al|por)\s*dia", t):
            req.max_daily_budget_eur = float(m.group(1))
    return req


def _best_sentences(text: str, query: str, n: int = 2) -> str:
    """Las `n` frases del fragmento que más palabras comparten con la pregunta, en su orden original."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    wanted = set(tokenize(query))
    ranked = sorted(range(len(sentences)), key=lambda i: (-len(wanted & set(tokenize(sentences[i]))), i))[:n]
    return " ".join(sentences[i] for i in sorted(ranked))


class DemoProvider:
    name = "demo"
    model = "rumbo-demo"

    def __init__(self, delay_s: float = 0.0) -> None:
        self._counter = 0
        self.delay_s = delay_s  # pausa artificial para que la demo se pueda seguir en pantalla

    def _id(self) -> str:
        self._counter += 1
        return f"toolu_demo_{self._counter:04d}"

    def complete(self, system: str, tools: list[dict], messages: list[dict]) -> ModelTurn:
        time.sleep(self.delay_s)
        user_texts = [m["content"] for m in messages if m["role"] == "user" and isinstance(m["content"], str)]
        req = parse_request(user_texts)

        # Herramientas ya ejecutadas en este turno (desde el último mensaje de texto del usuario).
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user" and isinstance(m["content"], str))
        done: dict[str, dict] = {}
        calls: dict[str, str] = {}
        for m in messages[last_user + 1 :]:
            for b in m["content"]:
                if b.get("type") == "tool_use":
                    calls[b["id"]] = b["name"]
                elif b.get("type") == "tool_result" and not b.get("is_error"):
                    done[calls[b["tool_use_id"]]] = json.loads(b["content"])

        if not req.destination_id and "search_destinations" in done:
            req.destination_id = done["search_destinations"]["results"][0]["destination_id"]

        # Guardarraíl de alcance: igual que el modelo real, el demo no responde a otros temas.
        if not is_travel_related(user_texts[-1]):
            return self._with_input(self._turn([Block(type="text", text=OFF_TOPIC_REPLY)], "end_turn"), messages)

        last = _norm(user_texts[-1])
        practical = bool(PRACTICAL.search(last))
        plan = bool(PLANNING.search(last)) or not practical
        # Una sola búsqueda por turno, aunque falle (si no, un error repetiría la llamada en bucle).
        if practical and "search_travel_guides" not in calls.values() and (req.destination_id or not plan):
            where = f" de {destinations()[req.destination_id]['name']}" if req.destination_id else ""
            return self._with_input(
                self._turn(
                    [
                        Block(type="text", text=f"Es una pregunta práctica: la busco en las guías{where} (RAG)."),
                        Block(
                            type="tool_use",
                            id=self._id(),
                            name="search_travel_guides",
                            input={"query": user_texts[-1], "destination_id": req.destination_id},
                        ),
                    ],
                    "tool_use",
                ),
                messages,
            )
        if not plan:
            text = self._guides_answer(done.get("search_travel_guides"))
            return self._with_input(self._turn([Block(type="text", text=text)], "end_turn"), messages)

        step = self._next_step(req, done)
        if step is None:
            return self._with_input(self._turn([Block(type="text", text=self._final_text(req, done))], "end_turn"), messages)
        narration, name, args = step
        return self._with_input(
            self._turn(
                [Block(type="text", text=narration), Block(type="tool_use", id=self._id(), name=name, input=args)], "tool_use"
            ),
            messages,
        )

    def _next_step(self, req: Request, done: dict) -> tuple[str, str, dict] | None:
        if not req.destination_id and "search_destinations" not in done:
            return (
                "Aún no tienes destino: busco los que mejor encajan con lo que pides.",
                "search_destinations",
                {
                    "interests": req.interests,
                    "month": req.month,
                    "style": req.style,
                    "max_daily_budget_eur": req.max_daily_budget_eur,
                },
            )
        dest = destinations()[req.destination_id]
        if req.month and "get_climate" not in done:
            return (
                f"Compruebo qué tiempo hace en {dest['name']} en {MONTHS[req.month - 1]}.",
                "get_climate",
                {"destination_id": req.destination_id, "month": req.month},
            )
        if "estimate_budget" not in done:
            return (
                "Calculo el presupuesto aproximado.",
                "estimate_budget",
                {"destination_id": req.destination_id, "days": req.days, "travelers": req.travelers, "style": req.style},
            )
        if "build_itinerary" not in done:
            return (
                f"Monto un itinerario de {req.days} días priorizando tus intereses.",
                "build_itinerary",
                {"destination_id": req.destination_id, "days": req.days, "interests": req.interests},
            )
        if "save_trip" not in done:
            title = f"{req.days} días en {dest['name']}" + (f" en {MONTHS[req.month - 1]}" if req.month else "")
            return (
                "Todo encaja. Guardo el viaje en tu panel.",
                "save_trip",
                {
                    "title": title,
                    "destination_id": req.destination_id,
                    "days": req.days,
                    "travelers": req.travelers,
                    "style": req.style,
                    "month": req.month,
                    "interests": req.interests,
                    "summary": f"{dest['description']} Plan {req.style} para {req.travelers} viajero(s).",
                },
            )
        return None

    def _final_text(self, req: Request, done: dict) -> str:
        dest = destinations()[req.destination_id]
        budget = done.get("estimate_budget", {})
        lines = [f"Listo: tu viaje de {req.days} días a {dest['name']} {dest['flag']} está guardado."]
        if climate := done.get("get_climate"):
            lines.append(f"En {climate['month']} la media es de {climate['avg_temp_c']} °C ({climate['verdict']}).")
        if budget:
            lines.append(
                f"Presupuesto estimado sin vuelos: {budget['total_eur']} € "
                f"({budget['total_per_person_eur']} € por persona, estilo {req.style})."
            )
        guides = done.get("search_travel_guides", {}).get("results") or []
        if guides:
            g = guides[0]
            tip = _best_sentences(g["text"], done["search_travel_guides"]["query"])
            lines.append(f"Consejo práctico: {tip} (Guía de {g['destination']} · {g['section']}).")
        lines.append("¿Quieres que lo haga más económico, añada días o cambie de destino?")
        return " ".join(lines)

    @staticmethod
    def _guides_answer(result: dict | None) -> str:
        """Respuesta extractiva: el modo demo no genera texto, cita el fragmento más relevante."""
        if result is None:
            return "Ahora mismo no he podido consultar las guías de viaje. Inténtalo de nuevo en unos minutos."
        hits = result.get("results") or []
        if not hits:
            return (
                "No tengo información sobre eso en mis guías de viaje, así que prefiero no inventarlo. "
                "Puedo ayudarte con documentación, dinero y propinas, transporte, seguridad, costumbres, "
                "enchufes, salud o dónde alojarte en cualquiera de mis 10 destinos."
            )
        top = hits[0]
        lines = [f"Según la guía de {top['destination']} ({top['section']}): {top['text']}"]
        lines.append(
            f"Fuente: Guía de {top['destination']} · {top['section']}. "
            "Es información orientativa: verifica los requisitos oficiales antes de viajar."
        )
        return "\n\n".join(lines)

    @staticmethod
    def _turn(blocks: list[Block], stop_reason: str) -> ModelTurn:
        content = []
        for b in blocks:
            if b.type == "text":
                content.append({"type": "text", "text": b.text})
            else:
                content.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        size = sum(len(json.dumps(c, ensure_ascii=False)) for c in content)
        return ModelTurn(stop_reason=stop_reason, blocks=blocks, history_content=content, input_tokens=0, output_tokens=size // 4)

    def _with_input(self, turn: ModelTurn, messages: list[dict]) -> ModelTurn:
        # Estimación aproximada (4 caracteres ≈ 1 token) para que la demo muestre métricas.
        turn.input_tokens = len(json.dumps(messages, ensure_ascii=False, default=str)) // 4
        return turn
