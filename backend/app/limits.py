"""Protección frente a abusos y control de gasto del modelo.

Tres capas, de fuera hacia dentro:

1. Anti-flood por IP: más de N peticiones por minuto al chat → HTTP 429.
2. Cupo de IA real por IP (por hora y por día): al agotarlo, esa persona sigue usando
   Rumbo en modo demo. Nunca ve un error.
3. Presupuesto diario global de tokens: al agotarlo, todo el mundo pasa al modo demo.
   Se fija por debajo de la cuota gratuita del proveedor, así que nunca se llega a ella.
   Si aun así el proveedor responde 429, se respeta su tiempo de espera (cooldown).

Los contadores viven en Redis si hay `REDIS_URL` (compartidos entre réplicas) o en memoria.
Son ventanas fijas (minuto, hora y día en UTC) con caducidad automática.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Protocol


class CounterStore(Protocol):
    def incr(self, key: str, amount: int, ttl_s: int) -> int: ...
    def get(self, key: str) -> int: ...
    def set(self, key: str, value: int, ttl_s: int) -> None: ...


class MemoryCounterStore:
    def __init__(self, clock=time.time) -> None:
        self._data: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def _alive(self, key: str) -> int:
        value, expires = self._data.get(key, (0, 0.0))
        if expires and expires <= self._clock():
            self._data.pop(key, None)
            return 0
        return value

    def incr(self, key: str, amount: int, ttl_s: int) -> int:
        with self._lock:
            current = self._alive(key)
            expires = self._data[key][1] if key in self._data else self._clock() + ttl_s
            self._data[key] = (current + amount, expires)
            # Limpieza perezosa para que el diccionario no crezca sin límite.
            if len(self._data) > 10_000:
                now = self._clock()
                self._data = {k: v for k, v in self._data.items() if v[1] > now}
            return current + amount

    def get(self, key: str) -> int:
        with self._lock:
            return self._alive(key)

    def set(self, key: str, value: int, ttl_s: int) -> None:
        with self._lock:
            self._data[key] = (value, self._clock() + ttl_s)


class RedisCounterStore:
    def __init__(self, client) -> None:
        self.redis = client

    def incr(self, key: str, amount: int, ttl_s: int) -> int:
        pipe = self.redis.pipeline()
        pipe.incrby(f"rumbo:limits:{key}", amount)
        pipe.expire(f"rumbo:limits:{key}", ttl_s, nx=True)
        return int(pipe.execute()[0])

    def get(self, key: str) -> int:
        return int(self.redis.get(f"rumbo:limits:{key}") or 0)

    def set(self, key: str, value: int, ttl_s: int) -> None:
        self.redis.set(f"rumbo:limits:{key}", value, ex=max(1, ttl_s))


@dataclass(frozen=True)
class LimitsConfig:
    flood_per_minute: int = 20
    llm_per_hour: int = 5
    llm_per_day: int = 15
    daily_token_budget: int = 180_000
    min_tokens_per_run: int = 12_000


class UsageLimits:
    def __init__(self, store: CounterStore, config: LimitsConfig, clock=time.time) -> None:
        self.store = store
        self.config = config
        self._clock = clock

    def _windows(self) -> tuple[str, str, str]:
        t = time.gmtime(self._clock())
        return time.strftime("%Y%m%d%H%M", t), time.strftime("%Y%m%d%H", t), time.strftime("%Y%m%d", t)

    # --- 1. Anti-flood -------------------------------------------------------------

    def allow_request(self, ip: str) -> bool:
        minute, _, _ = self._windows()
        return self.store.incr(f"flood:{ip}:{minute}", 1, 120) <= self.config.flood_per_minute

    # --- 2. Cupo de IA real por IP ----------------------------------------------------

    def ip_remaining(self, ip: str) -> dict[str, int]:
        _, hour, day = self._windows()
        return {
            "hour": max(0, self.config.llm_per_hour - self.store.get(f"ip:{ip}:h:{hour}")),
            "day": max(0, self.config.llm_per_day - self.store.get(f"ip:{ip}:d:{day}")),
        }

    def take_ip_quota(self, ip: str) -> bool:
        """Reserva una consulta con IA real para esta IP. False si ya no le quedan."""
        remaining = self.ip_remaining(ip)
        if remaining["hour"] <= 0 or remaining["day"] <= 0:
            return False
        _, hour, day = self._windows()
        self.store.incr(f"ip:{ip}:h:{hour}", 1, 3700)
        self.store.incr(f"ip:{ip}:d:{day}", 1, 90_000)
        return True

    # --- 3. Presupuesto global de tokens ----------------------------------------------

    def tokens_remaining(self) -> int:
        _, _, day = self._windows()
        return max(0, self.config.daily_token_budget - self.store.get(f"tokens:{day}"))

    def spend(self, tokens: int) -> None:
        if tokens > 0:
            _, _, day = self._windows()
            self.store.incr(f"tokens:{day}", tokens, 90_000)

    def cooldown(self, seconds: float) -> None:
        """El proveedor ha dicho "espera X segundos": nadie usa la IA real hasta entonces."""
        until = int(self._clock() + max(1.0, seconds))
        self.store.set("cooldown", until, int(max(1.0, seconds)) + 5)

    def cooling_down(self) -> bool:
        return self.store.get("cooldown") > self._clock()

    def can_start_run(self) -> bool:
        return not self.cooling_down() and self.tokens_remaining() >= self.config.min_tokens_per_run

    def can_call(self) -> bool:
        return not self.cooling_down() and self.tokens_remaining() > 0

    def status(self) -> dict:
        return {
            "available": self.can_start_run(),
            "budget_remaining_pct": round(100 * self.tokens_remaining() / max(1, self.config.daily_token_budget)),
            "per_ip": {"hour": self.config.llm_per_hour, "day": self.config.llm_per_day},
        }


def build_limits(redis_url: str | None, config: LimitsConfig) -> UsageLimits:
    if redis_url:
        import redis

        return UsageLimits(RedisCounterStore(redis.Redis.from_url(redis_url)), config)
    return UsageLimits(MemoryCounterStore(), config)


def client_ip(headers, peer: str | None) -> str:
    """IP del cliente.

    - Detrás de Cloudflare (Render lo usa), la cabecera CF-Connecting-IP trae la IP real del visitante.
    - Detrás de un proxy propio (nginx, Ingress), la última entrada de X-Forwarded-For es la que añade
      el proxy de confianza; las anteriores las puede inventar el cliente.

    Si alguien falseara la cabecera para saltarse el cupo por IP, el presupuesto diario global sigue
    limitando el gasto total."""
    for header in ("cf-connecting-ip", "true-client-ip"):
        if value := headers.get(header):
            return value.strip()
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[-1].strip() or (peer or "desconocida")
    return peer or "desconocida"
