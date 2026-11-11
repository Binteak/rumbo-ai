"""Proveedores de modelo.

El loop del agente no conoce ningún SDK: habla con un `ModelProvider` que devuelve
un `ModelTurn` normalizado. Así se puede cambiar de modelo, o usar el modo demo
sin API key, sin tocar el loop.

- `AnthropicProvider`: Claude.
- `OpenAICompatibleProvider`: cualquier API compatible con OpenAI (Gemini, Groq,
  Hugging Face, OpenRouter, DeepSeek...). Con sus planes gratuitos permite usar un modelo
  real sin coste.

El historial se guarda siempre en formato de bloques de Anthropic (text, tool_use,
tool_result); cada proveedor lo traduce a su API. Por eso se puede cambiar de proveedor,
o pasar al modo demo, a mitad de una conversación.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


@dataclass
class Block:
    type: str  # "text" | "tool_use"
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelTurn:
    stop_reason: str  # "tool_use" | "end_turn" | "max_tokens" | "refusal" | ...
    blocks: list[Block]
    history_content: Any  # contenido exacto que hay que guardar en el historial
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0  # tokens de entrada servidos desde caché (no cuentan para las cuotas de Groq)
    notice: str | None = None  # aviso para el usuario (p. ej. "paso al modo demo")


class RateLimited(Exception):
    """El proveedor ha rechazado la petición por cuota (HTTP 429)."""

    def __init__(self, retry_after: float | None, message: str = "") -> None:
        super().__init__(message or f"Cuota del proveedor agotada (reintentar en {retry_after} s)")
        self.retry_after = retry_after


class ProviderUnavailable(Exception):
    """El proveedor no está disponible (HTTP 5xx, sobrecarga o error de red) tras reintentar."""


# Errores temporales del proveedor: Gemini responde 503 cuando el modelo está saturado.
TRANSIENT_STATUS = {500, 502, 503, 504, 529}


class ModelProvider(Protocol):
    name: str
    model: str

    def complete(self, system: str, tools: list[dict], messages: list[dict]) -> ModelTurn: ...


class AnthropicProvider:
    """Claude vía la API de Anthropic."""

    name = "claude"

    def __init__(self, api_key: str, model: str, effort: str = "medium", max_tokens: int = 8000) -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    def complete(self, system: str, tools: list[dict], messages: list[dict]) -> ModelTurn:
        import anthropic

        try:
            return self._complete(system, tools, messages)
        except anthropic.RateLimitError as e:
            retry = e.response.headers.get("retry-after") if e.response is not None else None
            raise RateLimited(float(retry) if retry else None, str(e)) from e
        except (anthropic.InternalServerError, anthropic.APIConnectionError) as e:
            raise ProviderUnavailable(str(e)) from e

    def _complete(self, system: str, tools: list[dict], messages: list[dict]) -> ModelTurn:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            # Si un clasificador de seguridad rechaza la petición, la API reintenta
            # con un modelo de respaldo.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        blocks = []
        for b in response.content:
            if b.type == "text" and b.text:
                blocks.append(Block(type="text", text=b.text))
            elif b.type == "tool_use":
                blocks.append(Block(type="tool_use", id=b.id, name=b.name, input=dict(b.input)))
        usage = response.usage
        return ModelTurn(
            stop_reason=response.stop_reason or "end_turn",
            blocks=blocks,
            # Se guardan todos los bloques (incluidos los de thinking con su firma): la API los
            # necesita sin modificar. Como dicts JSON para poder persistirlos en Redis.
            history_content=[b.model_dump(mode="json", exclude_none=True) for b in response.content],
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )


# --- APIs compatibles con OpenAI (Groq, Gemini, OpenRouter...) -----------------------


def to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["input_schema"]}}
        for t in tools
    ]


def to_openai_messages(system: str, messages: list[dict], keep_extra: bool = True) -> list[dict]:
    """Traduce el historial (bloques de Anthropic) al formato de chat de OpenAI."""
    out: list[dict] = [{"role": "system", "content": system}]
    for m in messages:
        content = m["content"]
        if isinstance(content, str):
            out.append({"role": m["role"], "content": content})
            continue
        if m["role"] == "user":
            for b in content:
                if b.get("type") == "tool_result":
                    result = b.get("content", "")
                    out.append(
                        {
                            "role": "tool",
                            "tool_call_id": b["tool_use_id"],
                            "content": result if isinstance(result, str) else json.dumps(result, ensure_ascii=False),
                        }
                    )
                elif b.get("type") == "text":
                    out.append({"role": "user", "content": b["text"]})
            continue
        # Asistente: el texto va en `content` y las herramientas en `tool_calls` (los bloques de
        # razonamiento de Claude no tienen equivalente y se omiten).
        text = "\n".join(b["text"] for b in content if b.get("type") == "text" and b.get("text"))
        calls = []
        for b in content:
            if b.get("type") != "tool_use":
                continue
            call = {
                "id": b["id"],
                "type": "function",
                "function": {"name": b["name"], "arguments": json.dumps(b.get("input", {}), ensure_ascii=False)},
            }
            # Gemini 3 exige reenviar la "thought signature" que acompañaba a la llamada. Otros
            # proveedores pueden rechazar el campo, así que solo se envía a Gemini.
            if keep_extra and b.get("extra_content"):
                call["extra_content"] = b["extra_content"]
            calls.append(call)
        msg: dict[str, Any] = {"role": "assistant", "content": text or None}
        if calls:
            msg["tool_calls"] = calls
        if text or calls:
            out.append(msg)
    return out


def _retry_after(response: httpx.Response) -> float | None:
    header = response.headers.get("retry-after")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    # Groq también lo indica en el mensaje: "Please try again in 6m11.52s".
    if m := re.search(r"try again in (?:(\d+)m)?([\d.]+)s", response.text):
        return int(m.group(1) or 0) * 60 + float(m.group(2))
    return None


class OpenAICompatibleProvider:
    """Chat Completions con tool calling, con httpx (sin SDK)."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.groq.com/openai/v1",
        name: str = "groq",
        max_tokens: int = 2048,
        timeout_s: float = 45.0,
        transport: httpx.BaseTransport | None = None,
        retry_delays: tuple[float, ...] = (2.0, 5.0),
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.name = name
        self.model = model
        self.max_tokens = max_tokens
        self.retry_delays = retry_delays
        self.sleep = sleep
        self.client = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout_s, connect=10.0),
            transport=transport,
        )

    def _payload(self, system: str, tools: list[dict], messages: list[dict]) -> dict:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": to_openai_messages(system, messages, keep_extra=self.model.startswith("gemini")),
            "tools": to_openai_tools(tools),
            "tool_choice": "auto",
            "max_tokens": self.max_tokens,
            "temperature": 0.3,
        }
        if self.model.startswith(("openai/gpt-oss", "gemini")):
            payload["reasoning_effort"] = "low"  # menos tokens de razonamiento: cuidan la cuota gratuita
        return payload

    def complete(self, system: str, tools: list[dict], messages: list[dict]) -> ModelTurn:
        payload = self._payload(system, tools, messages)
        for attempt in range(2):
            r = self._post(payload)
            if r.status_code == 429:
                raise RateLimited(_retry_after(r), r.text[:300])
            # 402: créditos gratuitos agotados (Hugging Face, OpenRouter...). Se pausa una hora.
            if r.status_code == 402:
                raise RateLimited(3600, r.text[:300])
            # Clave inválida o sin permisos: que la cadena siga con el siguiente proveedor.
            if r.status_code in (401, 403):
                raise ProviderUnavailable(f"{self.name} rechaza la clave (HTTP {r.status_code})")
            # Algunos modelos abiertos generan a veces una llamada a herramienta mal formada
            # (Groq responde 400 "tool_use_failed"): se reintenta una vez.
            if r.status_code == 400 and "tool_use_failed" in r.text and attempt == 0:
                continue
            r.raise_for_status()
            return self._parse(r.json())
        raise RuntimeError("El modelo no ha generado una llamada a herramienta válida")

    def _post(self, payload: dict) -> httpx.Response:
        """POST con reintentos ante errores temporales (5xx, timeouts, red) y espera creciente."""
        last = ""
        for attempt in range(len(self.retry_delays) + 1):
            if attempt:
                self.sleep(self.retry_delays[attempt - 1])
            try:
                r = self.client.post("/chat/completions", json=payload)
            except httpx.ReadTimeout as e:
                # El modelo ya ha tardado el timeout entero: reintentar multiplicaría la espera.
                raise ProviderUnavailable(f"{self.name} no ha respondido a tiempo") from e
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = f"{type(e).__name__}: {e}"
                continue
            if r.status_code not in TRANSIENT_STATUS:
                return r
            last = f"HTTP {r.status_code}: {r.text[:200]}"
        raise ProviderUnavailable(f"{self.name} no disponible tras reintentar ({last})")

    @staticmethod
    def _parse(data: dict) -> ModelTurn:
        choice = data["choices"][0]
        msg = choice["message"]
        blocks: list[Block] = []
        extras: dict[str, dict] = {}
        if msg.get("content"):
            blocks.append(Block(type="text", text=msg["content"]))
        for call in msg.get("tool_calls") or []:
            call_id = call.get("id") or f"call_{uuid.uuid4().hex[:12]}"
            if call.get("extra_content"):
                extras[call_id] = call["extra_content"]
            raw = call["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                args = {"_argumentos_no_validos": raw}  # la validación Pydantic devolverá el error al modelo
            blocks.append(
                Block(type="tool_use", id=call_id, name=call["function"]["name"], input=args if isinstance(args, dict) else {})
            )
        if any(b.type == "tool_use" for b in blocks):
            stop = "tool_use"
        else:
            stop = {"length": "max_tokens", "content_filter": "refusal"}.get(choice.get("finish_reason"), "end_turn")
        history: list[dict] = []
        for b in blocks:
            if b.type == "text":
                history.append({"type": "text", "text": b.text})
            else:
                entry = {"type": "tool_use", "id": b.id, "name": b.name, "input": b.input}
                if b.id in extras:
                    entry["extra_content"] = extras[b.id]
                history.append(entry)
        usage = data.get("usage") or {}
        return ModelTurn(
            stop_reason=stop,
            blocks=blocks,
            history_content=history,
            input_tokens=usage.get("prompt_tokens", 0) or 0,
            output_tokens=usage.get("completion_tokens", 0) or 0,
            cached_tokens=(usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0,
        )
