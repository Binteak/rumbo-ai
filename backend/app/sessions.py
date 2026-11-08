"""Almacén del historial de conversación por sesión.

- `MemorySessionStore`: para desarrollo y tests (una sola instancia).
- `RedisSessionStore`: para producción con varias réplicas. El historial y el
  bloqueo por sesión viven en Redis, así que cualquier réplica puede atender
  el siguiente mensaje de una conversación (backend sin estado).
"""

from __future__ import annotations

import json
import threading
from typing import Protocol


class SessionLock(Protocol):
    def acquire(self, blocking: bool = ...) -> bool: ...
    def release(self) -> None: ...


class SessionStore(Protocol):
    def get(self, session_id: str) -> list[dict]: ...
    def save(self, session_id: str, history: list[dict]) -> None: ...
    def reset(self, session_id: str) -> None: ...
    def lock(self, session_id: str) -> SessionLock: ...
    def ping(self) -> bool: ...


class MemorySessionStore:
    def __init__(self) -> None:
        self._data: dict[str, list[dict]] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def get(self, session_id: str) -> list[dict]:
        with self._guard:
            return list(self._data.get(session_id, []))

    def save(self, session_id: str, history: list[dict]) -> None:
        with self._guard:
            self._data[session_id] = list(history)

    def reset(self, session_id: str) -> None:
        with self._guard:
            self._data.pop(session_id, None)

    def lock(self, session_id: str) -> SessionLock:
        with self._guard:
            return self._locks.setdefault(session_id, threading.Lock())

    def ping(self) -> bool:
        return True


class RedisSessionStore:
    def __init__(self, url: str, ttl_seconds: int = 24 * 3600, client=None) -> None:
        import redis

        self.redis = client or redis.Redis.from_url(url)
        self.ttl = ttl_seconds

    @staticmethod
    def _key(session_id: str) -> str:
        return f"rumbo:session:{session_id}"

    def get(self, session_id: str) -> list[dict]:
        raw = self.redis.get(self._key(session_id))
        return json.loads(raw) if raw else []

    def save(self, session_id: str, history: list[dict]) -> None:
        self.redis.set(self._key(session_id), json.dumps(history, ensure_ascii=False), ex=self.ttl)

    def reset(self, session_id: str) -> None:
        self.redis.delete(self._key(session_id))

    def lock(self, session_id: str) -> SessionLock:
        # Bloqueo distribuido: evita que dos réplicas procesen a la vez la misma conversación.
        # El timeout lo libera solo si una réplica muere a mitad.
        return self.redis.lock(f"rumbo:lock:{session_id}", timeout=180)

    def ping(self) -> bool:
        return bool(self.redis.ping())


def build_session_store(redis_url: str | None) -> SessionStore:
    return RedisSessionStore(redis_url) if redis_url else MemorySessionStore()
