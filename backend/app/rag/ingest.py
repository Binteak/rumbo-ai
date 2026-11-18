"""Ingesta: guías → fragmentos → embeddings → almacén de vectores, con la Indexing API de LangChain.

`index()` es incremental: el record manager guarda un hash de cada fragmento indexado, así que solo
se calculan embeddings de los nuevos o modificados, y con `cleanup="full"` se borran del almacén los
que ya no están en las guías. Repetirla sin cambios no cuesta nada. Se ejecuta al arrancar la API
y también a mano:

    python -m app.rag.ingest
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass

from langchain_core.indexing import RecordManager, index
from langchain_core.vectorstores import VectorStore

from .chunking import Chunk
from .store import store_name

log = logging.getLogger("rumbo.rag")


@dataclass
class IngestStats:
    chunks: int
    embedded: int  # fragmentos nuevos o modificados (los únicos que se envían al embedder)
    deleted: int
    embedder: str
    store: str
    duration_ms: int


def ingest(chunks: list[Chunk], store: VectorStore, records: RecordManager) -> IngestStats:
    started = time.perf_counter()
    result = index([c.to_document() for c in chunks], records, store, cleanup="full", key_encoder="sha256")
    stats = IngestStats(
        chunks=len(chunks),
        embedded=result["num_added"] + result["num_updated"],
        deleted=result["num_deleted"],
        embedder=getattr(store.embeddings, "name", "default"),
        store=store_name(store),
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    log.info("Ingesta RAG: %s", stats)
    return stats


if __name__ == "__main__":
    from . import get_rag

    logging.basicConfig(level=logging.INFO)
    print(json.dumps(asdict(get_rag().ingest_stats), indent=2, ensure_ascii=False))
