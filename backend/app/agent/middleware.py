"""Middleware de LangChain: cadena de modelos y control de gasto.

LangChain llama a `wrap_model_call` cada vez que el agente va a preguntar al modelo. Aquí:

1. Se prueban los modelos reales en orden (por ejemplo Gemini → Groq). Si uno falla por cuota
   o porque no responde, se pone en pausa y se sigue con el siguiente.
2. Si no queda ninguno, o se acaba el presupuesto diario de tokens, responde el modo demo.
3. Los tokens gastados se descuentan del presupuesto diario.

Cada cambio de modelo se le avisa al usuario en la traza (evento "notice").
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer
from langgraph.errors import GraphBubbleUp

from .models import Provider

log = logging.getLogger("rumbo.llm")


class Budget(Protocol):
    def can_call(self) -> bool: ...
    def spend(self, tokens: int) -> None: ...
    def cooldown(self, seconds: float, provider: str | None = None) -> None: ...
    def cooling_down(self, provider: str | None = None) -> bool: ...


class NoBudget:
    """Sin límites de gasto (tests y scripts)."""

    def can_call(self) -> bool:
        return True

    def spend(self, tokens: int) -> None:
        pass

    def cooldown(self, seconds: float, provider: str | None = None) -> None:
        pass

    def cooling_down(self, provider: str | None = None) -> bool:
        return False


class ModelChainMiddleware(AgentMiddleware):
    def __init__(self, providers: list[Provider], demo: Provider, budget: Budget) -> None:
        super().__init__()
        self.providers = providers
        self.demo = demo
        self.budget = budget
        self.current = providers[0] if providers else demo  # el modelo que está respondiendo

    def wrap_model_call(self, request: ModelRequest, handler: Any) -> ModelResponse:
        while self.current is not self.demo:
            provider = self.current
            if not self.budget.can_call():
                self._switch("Se ha agotado el presupuesto diario de IA real: continúo en modo demo.")
                break
            if self.budget.cooling_down(provider.name):
                self.current = self._next_available(provider)  # en pausa por otra petición: se salta sin avisar
                continue
            try:
                response = handler(request.override(model=provider.llm))
            except GraphBubbleUp:
                raise
            except Exception as e:  # noqa: BLE001 - cualquier fallo del proveedor pasa al siguiente modelo
                seconds, reason = _pause_for(e)
                log.warning("%s falla (%s): paso al siguiente modelo", provider.name, e)
                self.budget.cooldown(seconds, provider.name)
                self.current = self._next_available(provider)
                self._notify(f"{provider.label} {reason}: continúo con {self._target()}.")
                continue
            self.budget.spend(_tokens_used(response))
            return response
        return handler(request.override(model=self.demo.llm))

    def _next_available(self, failed: Provider) -> Provider:
        rest = self.providers[self.providers.index(failed) + 1 :]
        return next((p for p in rest if not self.budget.cooling_down(p.name)), self.demo)

    def _target(self) -> str:
        return "modo demo" if self.current is self.demo else self.current.label

    def _switch(self, text: str) -> None:
        self.current = self.demo
        self._notify(text)

    @staticmethod
    def _notify(text: str) -> None:
        get_stream_writer()({"type": "notice", "text": text})


def _pause_for(error: Exception) -> tuple[float, str]:
    """Cuánto tiempo pausar un proveedor tras un error, y cómo explicárselo al usuario."""
    status = getattr(error, "status_code", None) or getattr(getattr(error, "response", None), "status_code", None)
    if status == 429:
        headers = getattr(getattr(error, "response", None), "headers", None) or {}
        try:
            return float(headers.get("retry-after", 60)), "ha alcanzado su cuota gratuita"
        except ValueError:
            return 60, "ha alcanzado su cuota gratuita"
    if status == 402:  # créditos gratuitos agotados (Hugging Face, OpenRouter...)
        return 3600, "ha alcanzado su cuota gratuita"
    return 30, "no está disponible ahora mismo"


def _tokens_used(response: ModelResponse) -> int:
    """Tokens que cuentan para la cuota (los servidos desde caché no cuentan)."""
    total = 0
    for message in response.result:
        if isinstance(message, AIMessage) and message.usage_metadata:
            usage = message.usage_metadata
            cached = (usage.get("input_token_details") or {}).get("cache_read", 0) or 0
            total += usage.get("input_tokens", 0) - cached + usage.get("output_tokens", 0)
    return total
