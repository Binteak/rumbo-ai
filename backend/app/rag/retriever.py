"""Búsqueda híbrida: BM25 (palabras clave) + vectores (similitud), fusionadas con RRF.

- BM25 acierta cuando la pregunta usa las mismas palabras que la guía ("ESTA", "OMNY", "propina").
- Los vectores aciertan cuando usa otras palabras para lo mismo ("¿me hace falta papeleo?" → visado).
- Reciprocal Rank Fusion combina ambos rankings sin tener que calibrar sus puntuaciones,
  que están en escalas distintas: score = Σ peso / (k + posición).

Si el servicio de embeddings falla, la búsqueda sigue funcionando solo con BM25
(degradación controlada) y el resultado lo indica en `mode`.
"""

from __future__ import annotations

import logging
import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field

from .chunking import Chunk
from .embeddings import Embedder
from .store import VectorStore
from .text import expand_query, strip_accents, tokenize

log = logging.getLogger("rumbo.rag")
# Constante de RRF. El valor clásico es 60 (pensado para listas de cientos de candidatos); con 20
# candidatos, k=10 hace que la primera posición pese más. Elegido con `evals/rag_eval.py`.
RRF_K = 10
CANDIDATES = 20


class BM25:
    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = chunks
        self.k1, self.b = k1, b
        # El título de la sección cuenta doble: resume de qué trata el fragmento.
        self.docs = [Counter(tokenize(f"{c.destination} {c.section} {c.section} {c.text}")) for c in chunks]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg_len = sum(self.lengths) / max(1, len(self.lengths))
        df: Counter[str] = Counter()
        for doc in self.docs:
            df.update(doc.keys())
        n = len(chunks)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int, destination_id: str | None = None) -> list[tuple[str, float]]:
        terms = [t for t in set(tokenize(query)) if t in self.idf]
        scored = []
        for chunk, doc, length in zip(self.chunks, self.docs, self.lengths, strict=True):
            if destination_id and chunk.destination_id != destination_id:
                continue
            score = 0.0
            for t in terms:
                tf = doc.get(t, 0)
                if tf:
                    score += self.idf[t] * tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / self.avg_len))
            if score > 0:
                scored.append((chunk.id, score))
        return sorted(scored, key=lambda s: -s[1])[:k]


@dataclass
class Hit:
    chunk: Chunk
    score: float
    bm25_rank: int | None = None
    vector_rank: int | None = None
    vector_score: float | None = None

    def to_dict(self) -> dict:
        return {
            "source": self.chunk.source,
            "destination_id": self.chunk.destination_id,
            "destination": self.chunk.destination,
            "section": self.chunk.section,
            "text": self.chunk.text,
            "score": round(self.score, 4),
            "match": {
                "bm25_rank": self.bm25_rank,
                "vector_rank": self.vector_rank,
                "vector_similarity": round(self.vector_score, 3) if self.vector_score is not None else None,
            },
        }


@dataclass
class SearchResult:
    hits: list[Hit]
    mode: str  # "hybrid" | "bm25"
    destination_id: str | None = None  # filtro aplicado (indicado por el agente o detectado en la pregunta)
    expanded_terms: list[str] = field(default_factory=list)
    timings_ms: dict[str, float] = field(default_factory=dict)


class Retriever:
    def __init__(
        self,
        chunks: list[Chunk],
        embedder: Embedder,
        store: VectorStore,
        aliases: dict[str, str] | None = None,
        vector_weight: float | None = None,
    ) -> None:
        self.chunks = {c.id: c for c in chunks}
        # Peso del ranking vectorial en la fusión. Con embeddings semánticos (Voyage) ambos rankings
        # pesan igual; el embedder local por hashing aporta menos señal, así que pesa menos.
        self.vector_weight = vector_weight if vector_weight is not None else (0.3 if embedder.name.startswith("hashing") else 1.0)
        self.embedder = embedder
        self.store = store
        self.bm25 = BM25(chunks)
        # alias normalizado ("japon", "nueva york") -> destination_id
        self.aliases = {strip_accents(a): d for a, d in (aliases or {}).items()}

    def detect_destination(self, query: str) -> str | None:
        """Si la pregunta nombra un único destino ("¿visado para Japón?"), se filtra por él."""
        q = strip_accents(query)
        found = {d for alias, d in self.aliases.items() if re.search(rf"\b{re.escape(alias)}\b", q)}
        return found.pop() if len(found) == 1 else None

    def search(self, query: str, k: int = 4, destination_id: str | None = None) -> SearchResult:
        timings: dict[str, float] = {}
        destination_id = destination_id or self.detect_destination(query)
        t0 = time.perf_counter()
        expanded, added = expand_query(query)
        lexical = self.bm25.search(expanded, CANDIDATES, destination_id)
        timings["bm25"] = round((time.perf_counter() - t0) * 1000, 1)

        mode, semantic = "hybrid", []
        t0 = time.perf_counter()
        try:
            qvec = self.embedder.embed_query(query)
            semantic = self.store.search(self.embedder.name, qvec, CANDIDATES, destination_id)
        except Exception as e:  # noqa: BLE001 - si los embeddings fallan, seguimos solo con BM25
            log.warning("Búsqueda vectorial no disponible (%s): se usa solo BM25", e)
            mode = "bm25"
        timings["vector"] = round((time.perf_counter() - t0) * 1000, 1)

        hits: dict[str, Hit] = {}
        for rank, (cid, _) in enumerate(lexical, start=1):
            hit = hits.setdefault(cid, Hit(self.chunks[cid], 0.0))
            hit.bm25_rank, hit.score = rank, hit.score + 1 / (RRF_K + rank)
        for rank, (cid, sim) in enumerate(semantic, start=1):
            if cid not in self.chunks:  # fila antigua en la BD que ya no está en las guías
                continue
            hit = hits.setdefault(cid, Hit(self.chunks[cid], 0.0))
            hit.vector_rank, hit.vector_score = rank, sim
            hit.score += self.vector_weight / (RRF_K + rank)

        # Sin ninguna coincidencia de palabras, solo se aceptan resultados vectoriales con similitud
        # suficiente: así una pregunta fuera de las guías devuelve "sin resultados" en lugar de ruido.
        if not lexical:
            hits = {cid: h for cid, h in hits.items() if (h.vector_score or 0) >= 0.35}
        ranked = sorted(hits.values(), key=lambda h: -h.score)[:k]
        return SearchResult(ranked, mode, destination_id, added, timings)
