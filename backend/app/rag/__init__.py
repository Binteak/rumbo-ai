"""RAG sobre las guías prácticas de cada destino.

Punto de entrada: `get_rag()` construye (una vez por proceso) el retriever listo
para usar, eligiendo embedder y almacén según la configuración:

    VOYAGE_API_KEY    → embeddings de Voyage AI (si no, embedder local por hashing)
    DATABASE_URL      → PostgreSQL + pgvector (si no, almacén en memoria)

Si Voyage falla al arrancar, se recurre al embedder local para que la API
arranque igualmente.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

from .chunking import Chunk, load_chunks
from .embeddings import HashingEmbedder, build_embedder
from .ingest import IngestStats, ingest
from .retriever import Retriever, SearchResult
from .store import build_store

log = logging.getLogger("rumbo.rag")

__all__ = ["Chunk", "Rag", "Retriever", "SearchResult", "get_rag"]


@dataclass
class Rag:
    retriever: Retriever
    ingest_stats: IngestStats

    def status(self) -> dict:
        return {
            "chunks": self.ingest_stats.chunks,
            "embedder": self.ingest_stats.embedder,
            "store": self.ingest_stats.store,
            "search": "hybrid (BM25 + vector, RRF)",
        }


@lru_cache
def get_rag() -> Rag:
    from ..config import get_settings
    from ..db import engine

    settings = get_settings()
    chunks = load_chunks()
    store = build_store(engine)
    embedder = build_embedder(settings.voyage_api_key, settings.embedding_model)
    try:
        stats = ingest(chunks, embedder, store)
    except Exception as e:  # noqa: BLE001 - p. ej. clave de Voyage inválida o sin red
        log.warning("Embedder %s no disponible (%s): se usa el embedder local", embedder.name, e)
        embedder = HashingEmbedder()
        stats = ingest(chunks, embedder, store)
    return Rag(Retriever(chunks, embedder, store, _destination_aliases()), stats)


def _destination_aliases() -> dict[str, str]:
    from ..agent.tools import destinations

    aliases = {
        "japon": "kioto",
        "kyoto": "kioto",
        "new york": "nuevayork",
        "nyc": "nuevayork",
        "corea": "seul",
        "sudafrica": "ciudaddelcabo",
        "mexico": "cdmx",
        "df": "cdmx",
    }
    for d in destinations().values():
        aliases[d["name"]] = d["id"]
        aliases[d["country"]] = d["id"]
    return aliases
