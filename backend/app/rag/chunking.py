"""Carga de las guías y troceado (chunking).

Cada guía es un Markdown por destino (`data/guides/<destination_id>.md`). Se trocea
por secciones `##` porque cada sección responde a un tema concreto (visado,
transporte, propinas...): así un fragmento recuperado es una respuesta completa y
la cita "Guía de Kioto · Cómo moverse" tiene sentido para el usuario.

Si una sección es muy larga se divide por párrafos y frases, con solapamiento de
una frase para no cortar una idea por la mitad.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .text import strip_accents

GUIDES_DIR = Path(__file__).resolve().parent.parent / "data" / "guides"
MAX_CHARS = 900
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    id: str
    destination_id: str
    destination: str
    section: str
    text: str
    source: str

    @property
    def embedding_text(self) -> str:
        """Texto que se convierte en vector: incluye destino y sección como contexto.

        Un fragmento como "La moneda es el yen" se recupera mejor si el vector
        también sabe que es de la guía de Kioto, sección "Dinero y propinas".
        """
        return f"{self.destination} · {self.section}\n{self.text}"

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.embedding_text.encode("utf-8")).hexdigest()[:16]


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", strip_accents(text)).strip("-")


def _split_long(text: str, max_chars: int) -> list[str]:
    """Divide un texto largo en trozos de como mucho `max_chars`, solapando una frase."""
    if len(text) <= max_chars:
        return [text]
    sentences = [s for s in _SENTENCE_END.split(text) if s]
    parts, current = [], []
    for sentence in sentences:
        if current and len(" ".join([*current, sentence])) > max_chars:
            parts.append(" ".join(current))
            current = [current[-1]]  # solapamiento: la última frase abre el siguiente trozo
        current.append(sentence)
    if current:
        parts.append(" ".join(current))
    return parts


def chunk_guide(markdown: str, destination_id: str, source: str, max_chars: int = MAX_CHARS) -> list[Chunk]:
    title_match = re.search(r"^# (.+)$", markdown, flags=re.MULTILINE)
    title = title_match.group(1).strip() if title_match else destination_id
    destination = re.sub(r"^Guía práctica de\s+", "", title)

    chunks: list[Chunk] = []
    # Cada bloque empieza con "## Sección"; lo anterior a la primera sección es la introducción.
    for block in re.split(r"^## ", markdown, flags=re.MULTILINE)[1:]:
        heading, _, body = block.partition("\n")
        section = heading.strip()
        paragraphs = [" ".join(p.split()) for p in body.strip().split("\n\n") if p.strip()]
        text = " ".join(paragraphs)
        for n, part in enumerate(_split_long(text, max_chars)):
            chunks.append(
                Chunk(
                    id=f"{destination_id}#{_slug(section)}#{n}",
                    destination_id=destination_id,
                    destination=destination,
                    section=section,
                    text=part,
                    source=source,
                )
            )
    return chunks


def load_chunks(guides_dir: Path = GUIDES_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(guides_dir.glob("*.md")):
        chunks.extend(chunk_guide(path.read_text(encoding="utf-8"), path.stem, f"guides/{path.name}"))
    return chunks
