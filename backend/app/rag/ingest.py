"""Ingesta: guías → fragmentos → embeddings → almacén de vectores.

Es incremental: solo se calculan embeddings de los fragmentos nuevos o modificados
(se compara un hash del contenido), así que repetirla no cuesta nada si no hay cambios.
Se ejecuta al arrancar la API y también a mano:

    python -m app.rag.ingest
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass

from .chunking import Chunk
from .embeddings import Embedder
from .store import VectorStore

log = logging.getLogger("rumbo.rag")


@dataclass
class IngestStats:
    chunks: int
    embedded: int
    deleted: int
    embedder: str
    store: str
    duration_ms: int


def ingest(chunks: list[Chunk], embedder: Embedder, store: VectorStore) -> IngestStats:
    started = time.perf_counter()
    existing = store.existing_hashes(embedder.name)
    pending = [c for c in chunks if existing.get(c.id) != c.content_hash]
    if pending:
        vectors = embedder.embed_documents([c.embedding_text for c in pending])
        store.upsert(embedder.name, pending, vectors)
    deleted = store.delete_missing(embedder.name, {c.id for c in chunks})
    stats = IngestStats(
        chunks=len(chunks),
        embedded=len(pending),
        deleted=deleted,
        embedder=embedder.name,
        store=store.name,
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    log.info("Ingesta RAG: %s", stats)
    return stats


if __name__ == "__main__":
    from . import get_rag

    logging.basicConfig(level=logging.INFO)
    print(json.dumps(asdict(get_rag().ingest_stats), indent=2, ensure_ascii=False))
