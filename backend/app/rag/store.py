"""Almacenes de vectores de LangChain.

- `PGVector` (`langchain-postgres`): PostgreSQL con la extensión pgvector. Los vectores persisten
  y la similitud coseno se calcula en la base de datos. Es el que se usa en Docker Compose y Kubernetes.
- `InMemoryVectorStore` (`langchain-core`): en memoria, para SQLite en local, la demo, los tests
  y la CI. Con unos cientos de fragmentos, un recorrido exacto tarda microsegundos.

Cada embedder tiene su propia colección: si cambias de embedder (por ejemplo, añades la clave
de Voyage) se indexa de nuevo sin mezclar vectores incompatibles.

Junto al almacén va su *record manager*, que recuerda qué fragmentos ya están indexados para que
la ingesta solo calcule embeddings de lo nuevo o modificado (ver `ingest.py`).
"""

from __future__ import annotations

import logging

from langchain_core.embeddings import Embeddings
from langchain_core.indexing import InMemoryRecordManager, RecordManager
from langchain_core.vectorstores import InMemoryVectorStore, VectorStore
from sqlalchemy.engine import Engine

log = logging.getLogger("rumbo.rag")


# Nombre corto del almacén para /api/rag/status y los logs.
def store_name(store: VectorStore) -> str:
    return "pgvector" if type(store).__name__ == "PGVector" else "memory"


def build_store(engine: Engine, embedder: Embeddings) -> tuple[VectorStore, RecordManager]:
    """pgvector si la base de datos es PostgreSQL y la extensión está disponible; si no, memoria."""
    name = getattr(embedder, "name", "default")
    if engine.dialect.name == "postgresql":
        try:
            from langchain_classic.indexes import SQLRecordManager
            from langchain_postgres import PGVector

            # Tablas de LangChain (langchain_pg_collection y langchain_pg_embedding); metadatos en JSONB para filtrar.
            store = PGVector(embedder, connection=engine, collection_name=f"rag:{name}", use_jsonb=True)
            # Registro de lo ya indexado, en la misma base de datos.
            records = SQLRecordManager(f"rag:{name}", engine=engine)
            records.create_schema()
            return store, records
        except Exception as e:  # noqa: BLE001 - p. ej. PostgreSQL sin la extensión instalada
            log.warning("pgvector no disponible (%s): se usa el almacén en memoria", e)
    return build_memory_store(embedder)


# Almacén y registro en memoria: se reconstruyen en cada arranque (con 84 fragmentos tarda milisegundos).
def build_memory_store(embedder: Embeddings) -> tuple[VectorStore, RecordManager]:
    records = InMemoryRecordManager(f"rag:{getattr(embedder, 'name', 'default')}")
    records.create_schema()
    return InMemoryVectorStore(embedder), records


def vector_search(store: VectorStore, vector: list[float], k: int, destination_id: str | None = None) -> list[tuple[str, float]]:
    """Los `k` fragmentos más parecidos al vector: [(chunk_id, similitud coseno)], de más a menos parecido.

    Cada almacén de LangChain filtra y puntúa a su manera: PGVector filtra con un dict sobre los
    metadatos y devuelve la *distancia* coseno; InMemoryVectorStore filtra con una función y
    devuelve la *similitud*. Aquí se unifican.
    """
    if store_name(store) == "pgvector":
        where = {"destination_id": destination_id} if destination_id else None
        found = store.similarity_search_with_score_by_vector(vector, k=k, filter=where)
        return [(doc.metadata["chunk_id"], 1 - distance) for doc, distance in found]
    keep = (lambda doc: doc.metadata["destination_id"] == destination_id) if destination_id else None
    found = store.similarity_search_with_score_by_vector(vector, k=k, filter=keep)
    return [(doc.metadata["chunk_id"], similarity) for doc, similarity in found]
