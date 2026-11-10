"""Almacenes de vectores.

- `PgVectorStore`: PostgreSQL con la extensión pgvector. Los vectores persisten y la
  búsqueda por similitud coseno se hace en la base de datos (operador `<=>`).
  Es el que se usa en Docker Compose y Kubernetes.
- `MemoryVectorStore`: en memoria, para SQLite en local, tests y entornos sin
  pgvector. Con unos cientos de fragmentos un recorrido exacto tarda microsegundos.

Cada fila guarda el embedder que la generó: si cambias de embedder (por ejemplo,
añades la clave de Voyage) se reindexa sin mezclar vectores incompatibles.
"""

from __future__ import annotations

import logging
from typing import Protocol

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .chunking import Chunk

log = logging.getLogger("rumbo.rag")


class VectorStore(Protocol):
    name: str

    def existing_hashes(self, embedder: str) -> dict[str, str]: ...
    def upsert(self, embedder: str, chunks: list[Chunk], vectors: list[list[float]]) -> None: ...
    def delete_missing(self, embedder: str, keep_ids: set[str]) -> int: ...
    def search(
        self, embedder: str, vector: list[float], k: int, destination_id: str | None = None
    ) -> list[tuple[str, float]]: ...


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


class MemoryVectorStore:
    name = "memory"

    def __init__(self) -> None:
        # embedder -> chunk_id -> (destination_id, hash, vector)
        self._rows: dict[str, dict[str, tuple[str, str, list[float]]]] = {}

    def existing_hashes(self, embedder: str) -> dict[str, str]:
        return {cid: row[1] for cid, row in self._rows.get(embedder, {}).items()}

    def upsert(self, embedder: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        rows = self._rows.setdefault(embedder, {})
        for chunk, vec in zip(chunks, vectors, strict=True):
            rows[chunk.id] = (chunk.destination_id, chunk.content_hash, vec)

    def delete_missing(self, embedder: str, keep_ids: set[str]) -> int:
        rows = self._rows.get(embedder, {})
        stale = [cid for cid in rows if cid not in keep_ids]
        for cid in stale:
            del rows[cid]
        return len(stale)

    def search(self, embedder: str, vector: list[float], k: int, destination_id: str | None = None) -> list[tuple[str, float]]:
        # Los vectores están normalizados: el producto escalar es la similitud coseno.
        scored = [
            (cid, _dot(vec, vector))
            for cid, (dest, _, vec) in self._rows.get(embedder, {}).items()
            if destination_id is None or dest == destination_id
        ]
        return sorted(scored, key=lambda s: -s[1])[:k]


def _vector_literal(vec: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vec) + "]"


class PgVectorStore:
    """pgvector sin dependencias extra: los vectores viajan como literal '[0.1,...]' y se convierten con CAST."""

    name = "pgvector"

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        with engine.begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(727275)"))  # varias réplicas arrancando a la vez
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            # Columna `vector` sin dimensión fija: admite embedders de distinto tamaño (filtrados por `embedder`).
            # Con pocos miles de fragmentos la búsqueda exacta es suficiente; si crece, se añadiría un índice HNSW.
            conn.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS rag_chunks (
                        id TEXT NOT NULL,
                        embedder TEXT NOT NULL,
                        destination_id TEXT NOT NULL,
                        section TEXT NOT NULL,
                        content_hash TEXT NOT NULL,
                        embedding vector NOT NULL,
                        PRIMARY KEY (id, embedder)
                    )
                    """
                )
            )

    def existing_hashes(self, embedder: str) -> dict[str, str]:
        with self.engine.connect() as conn:
            rows = conn.execute(text("SELECT id, content_hash FROM rag_chunks WHERE embedder = :e"), {"e": embedder})
            return {r.id: r.content_hash for r in rows}

    def upsert(self, embedder: str, chunks: list[Chunk], vectors: list[list[float]]) -> None:
        if not chunks:
            return
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO rag_chunks (id, embedder, destination_id, section, content_hash, embedding)
                    VALUES (:id, :e, :d, :s, :h, CAST(:v AS vector))
                    ON CONFLICT (id, embedder) DO UPDATE
                    SET destination_id = EXCLUDED.destination_id, section = EXCLUDED.section,
                        content_hash = EXCLUDED.content_hash, embedding = EXCLUDED.embedding
                    """
                ),
                [
                    {
                        "id": c.id,
                        "e": embedder,
                        "d": c.destination_id,
                        "s": c.section,
                        "h": c.content_hash,
                        "v": _vector_literal(v),
                    }
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )

    def delete_missing(self, embedder: str, keep_ids: set[str]) -> int:
        stale = set(self.existing_hashes(embedder)) - keep_ids
        if stale:
            with self.engine.begin() as conn:
                conn.execute(
                    text("DELETE FROM rag_chunks WHERE embedder = :e AND id = ANY(:ids)"), {"e": embedder, "ids": list(stale)}
                )
        return len(stale)

    def search(self, embedder: str, vector: list[float], k: int, destination_id: str | None = None) -> list[tuple[str, float]]:
        where = "embedder = :e" + (" AND destination_id = :d" if destination_id else "")
        sql = text(
            f"""
            SELECT id, 1 - (embedding <=> CAST(:q AS vector)) AS score
            FROM rag_chunks WHERE {where}
            ORDER BY embedding <=> CAST(:q AS vector)
            LIMIT :k
            """  # noqa: S608 - `where` solo combina fragmentos fijos; los valores van como parámetros
        )
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"e": embedder, "d": destination_id, "q": _vector_literal(vector), "k": k})
            return [(r.id, float(r.score)) for r in rows]


def build_store(engine: Engine) -> VectorStore:
    """pgvector si la base de datos es PostgreSQL y la extensión está disponible; si no, memoria."""
    if engine.dialect.name == "postgresql":
        try:
            return PgVectorStore(engine)
        except Exception as e:  # noqa: BLE001 - p. ej. PostgreSQL sin la extensión instalada
            log.warning("pgvector no disponible (%s): se usa el almacén en memoria", e)
    return MemoryVectorStore()
