"""Proveedor protegido: usa el modelo real mientras haya presupuesto y, si no, el modo demo.

Envuelve al proveedor real (Claude o Groq) durante una ejecución del agente:

- Antes de cada llamada comprueba el presupuesto global; después descuenta los tokens usados
  (sin contar los servidos desde caché, que Groq no cuenta en sus cuotas).
- Si el proveedor responde 429 con una espera corta (límite por minuto), espera y reintenta.
  Si la espera es larga (cuota diaria), activa un cooldown global y pasa al modo demo.
- Al pasar al modo demo a mitad de un turno, el aviso viaja en `ModelTurn.notice` y el loop
  lo muestra en la traza. El historial es compatible porque todos usan el mismo formato.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Protocol

from .providers import ModelProvider, ModelTurn, RateLimited

log = logging.getLogger("rumbo.llm")


class Budget(Protocol):
    def can_call(self) -> bool: ...
    def spend(self, tokens: int) -> None: ...
    def cooldown(self, seconds: float) -> None: ...


class GuardedProvider:
    def __init__(
        self,
        primary: ModelProvider,
        fallback: ModelProvider,
        budget: Budget,
        max_wait_s: float = 20.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.primary = primary
        self.fallback = fallback
        self.budget = budget
        self.max_wait_s = max_wait_s
        self.sleep = sleep
        self.switched = False

    @property
    def name(self) -> str:
        return self.fallback.name if self.switched else self.primary.name

    @property
    def model(self) -> str:
        return self.fallback.model if self.switched else self.primary.model

    def complete(self, system: str, tools: list[dict], messages: list[dict]) -> ModelTurn:
        notice = None
        if not self.switched:
            if self.budget.can_call():
                for attempt in range(3):
                    try:
                        turn = self.primary.complete(system, tools, messages)
                        self.budget.spend(turn.input_tokens - turn.cached_tokens + turn.output_tokens)
                        return turn
                    except RateLimited as e:
                        wait = e.retry_after
                        if wait is not None and wait <= self.max_wait_s and attempt < 2:
                            log.info("Límite por minuto del proveedor: espero %.1f s", wait)
                            self.sleep(wait + 0.5)
                            continue
                        log.warning("Cuota del proveedor agotada (%s): paso al modo demo", e)
                        self.budget.cooldown(wait or 60)
                        break
                notice = "El proveedor de IA ha alcanzado su cuota gratuita: continúo en modo demo."
            else:
                notice = "Se ha agotado el presupuesto diario de IA real: continúo en modo demo."
            self.switched = True
        turn = self.fallback.complete(system, tools, messages)
        turn.notice = notice
        return turn
