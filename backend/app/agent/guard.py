"""Proveedor protegido: recorre la cadena de modelos reales y, al final, usa el modo demo.

Envuelve a los proveedores reales configurados (por ejemplo Gemini → Groq → Hugging Face)
durante una ejecución del agente:

- Antes de cada llamada comprueba el presupuesto global; después descuenta los tokens usados
  (sin contar los servidos desde caché, que los proveedores no cuentan en sus cuotas).
- Si un proveedor responde 429 con una espera corta (límite por minuto), espera y reintenta.
- Si la espera es larga (cuota diaria agotada), si se quedan sin créditos o si no responde,
  ese proveedor entra en pausa (cooldown propio) y el turno sigue con el siguiente de la cadena.
- Cuando no queda ninguno, el turno sigue en modo demo.
- Cada cambio de proveedor viaja como aviso en `ModelTurn.notice` y el loop lo muestra en la
  traza. El historial es compatible porque todos usan el mismo formato.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from typing import Protocol

from .providers import ModelProvider, ModelTurn, ProviderUnavailable, RateLimited

log = logging.getLogger("rumbo.llm")

LABELS = {"claude": "Claude", "gemini": "Gemini", "groq": "Groq", "huggingface": "Hugging Face", "openrouter": "OpenRouter"}


def label(name: str) -> str:
    """Nombre legible del proveedor para los avisos: "huggingface" → "Hugging Face"."""
    return LABELS.get(name, name[:1].upper() + name[1:])


class Budget(Protocol):
    def can_call(self) -> bool: ...
    def spend(self, tokens: int) -> None: ...
    def cooldown(self, seconds: float, provider: str | None = None) -> None: ...
    def cooling_down(self, provider: str | None = None) -> bool: ...


class GuardedProvider:
    def __init__(
        self,
        primary: ModelProvider | Sequence[ModelProvider],
        fallback: ModelProvider,
        budget: Budget,
        max_wait_s: float = 20.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.chain: list[ModelProvider] = list(primary) if isinstance(primary, Sequence) else [primary]
        self.index = 0  # proveedor de la cadena que atiende ahora
        self.fallback = fallback
        self.budget = budget
        self.max_wait_s = max_wait_s
        self.sleep = sleep
        self.switched = not self.chain  # True: ya se usa el modo demo

    @property
    def current(self) -> ModelProvider:
        return self.fallback if self.switched else self.chain[self.index]

    @property
    def primary(self) -> ModelProvider:
        return self.chain[0] if self.chain else self.fallback

    @property
    def name(self) -> str:
        return self.current.name

    @property
    def model(self) -> str:
        return self.current.model

    def complete(self, system: str, tools: list[dict], messages: list[dict]) -> ModelTurn:
        notices: list[str] = []
        while not self.switched:
            if not self.budget.can_call():
                notices.append("Se ha agotado el presupuesto diario de IA real: continúo en modo demo.")
                self.switched = True
                break
            provider = self.chain[self.index]
            if self.budget.cooling_down(provider.name):
                self._next(provider, None, notices)  # en pausa por otra petición: se salta sin avisar
                continue
            try:
                turn = self._call(provider, system, tools, messages)
            except RateLimited as e:
                log.warning("Cuota de %s agotada (%s): paso al siguiente proveedor", provider.name, e)
                self.budget.cooldown(e.retry_after or 60, provider.name)
                self._next(provider, "ha alcanzado su cuota gratuita", notices)
                continue
            except ProviderUnavailable as e:
                # Sobrecarga temporal (p. ej. Gemini 503) o clave inválida: pausa breve y siguiente.
                log.warning("%s no disponible (%s): paso al siguiente proveedor", provider.name, e)
                self.budget.cooldown(30, provider.name)
                self._next(provider, "no está disponible ahora mismo", notices)
                continue
            turn.notice = " ".join(notices) or None
            return turn
        turn = self.fallback.complete(system, tools, messages)
        turn.notice = " ".join(notices) or None
        return turn

    def _call(self, provider: ModelProvider, system: str, tools: list[dict], messages: list[dict]) -> ModelTurn:
        """Llama al proveedor esperando si el límite es por minuto (espera corta)."""
        for attempt in range(3):
            try:
                turn = provider.complete(system, tools, messages)
            except RateLimited as e:
                wait = e.retry_after
                if wait is not None and wait <= self.max_wait_s and attempt < 2:
                    log.info("Límite por minuto de %s: espero %.1f s", provider.name, wait)
                    self.sleep(wait + 0.5)
                    continue
                raise
            self.budget.spend(turn.input_tokens - turn.cached_tokens + turn.output_tokens)
            return turn
        raise RateLimited(None)  # no se llega: el último intento devuelve o lanza

    def _next(self, provider: ModelProvider, reason: str | None, notices: list[str]) -> None:
        """Avanza al siguiente proveedor de la cadena o, si no quedan, al modo demo."""
        self.index += 1
        if self.index < len(self.chain):
            if reason:
                notices.append(f"{label(provider.name)} {reason}: continúo con {label(self.chain[self.index].name)}.")
            return
        self.switched = True
        if reason:
            notices.append(f"{label(provider.name)} {reason}: continúo en modo demo.")
        elif not notices:
            notices.append("Los modelos de IA real están en pausa: continúo en modo demo.")
