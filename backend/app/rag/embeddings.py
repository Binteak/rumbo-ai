"""Embedders: convierten texto en vectores.

Igual que el agente habla con un `ModelProvider`, el RAG habla con un `Embedder`:

- `VoyageEmbedder`: embeddings semánticos multilingües de Voyage AI (el proveedor
  que recomienda Anthropic, ya que Claude no genera embeddings). Se usa en
  producción cuando hay `VOYAGE_API_KEY`.
- `HashingEmbedder`: local, gratis y determinista (hashing de palabras y
  n-gramas de caracteres). No entiende sinónimos, pero tolera plurales, tildes y
  erratas. Hace que la demo, los tests y la CI funcionen sin red ni coste.
"""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

import httpx

from .text import strip_accents, tokenize


class Embedder(Protocol):
    name: str
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class HashingEmbedder:
    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _bucket(self, feature: str) -> tuple[int, float]:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        return value % self.dim, 1.0 if (value >> 63) & 1 else -1.0

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        features = [f"w:{t}" for t in tokenize(text)]
        # N-gramas de caracteres: "visado" y "visados" comparten casi todos.
        for word in strip_accents(text).split():
            padded = f"<{word}>"
            features += [f"c:{padded[i : i + 4]}" for i in range(max(1, len(padded) - 3))]
        for feature in features:
            idx, sign = self._bucket(feature)
            vec[idx] += sign * (2.0 if feature.startswith("w:") else 0.5)
        return _normalize(vec)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class VoyageEmbedder:
    """Cliente mínimo de la API de embeddings de Voyage AI (sin SDK: un POST con httpx)."""

    BATCH = 128

    def __init__(
        self, api_key: str, model: str = "voyage-4-lite", timeout_s: float = 15.0, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.model = model
        self.name = f"voyage:{model}"
        self.dim = 1024
        # Las claves emitidas desde MongoDB Atlas (prefijo "al-") usan otro host.
        base = "https://ai.mongodb.com/v1" if api_key.startswith("al-") else "https://api.voyageai.com/v1"
        self.client = httpx.Client(
            base_url=base, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout_s, transport=transport
        )

    def _embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for i in range(0, len(texts), self.BATCH):
            batch = texts[i : i + self.BATCH]
            r = self.client.post("/embeddings", json={"input": batch, "model": self.model, "input_type": input_type})
            r.raise_for_status()
            data = sorted(r.json()["data"], key=lambda d: d["index"])
            vectors.extend(d["embedding"] for d in data)
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts, "document")

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "query")[0]


def build_embedder(voyage_api_key: str | None, model: str) -> Embedder:
    return VoyageEmbedder(voyage_api_key, model) if voyage_api_key else HashingEmbedder()
