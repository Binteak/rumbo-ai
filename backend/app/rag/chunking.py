"""Carga de las guías y troceado (chunking) con los splitters de LangChain.

Cada guía es un Markdown por destino (`data/guides/<destination_id>.md`). Se trocea
por secciones `##` (`MarkdownHeaderTextSplitter`) porque cada sección responde a un tema
concreto (visado, transporte, propinas...): así un fragmento recuperado es una respuesta
completa y la cita "Guía de Kioto · Cómo moverse" tiene sentido para el usuario.

Si una sección es muy larga, `RecursiveCharacterTextSplitter` la divide por frases,
con solapamiento para no cortar una idea por la mitad.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from .text import strip_accents

# Guías en Markdown, una por destino.
GUIDES_DIR = Path(__file__).resolve().parent.parent / "data" / "guides"
# Tamaño máximo de un fragmento; las secciones más largas se dividen.
MAX_CHARS = 900


# Fragmento de una guía: una sección (o un trozo de una sección larga) con su origen.
# El id es "<destino>#<sección>#<n>", por ejemplo "kioto#como-moverse#0".
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

    def to_document(self) -> Document:
        """El fragmento como `Document` de LangChain, que es lo que guarda el almacén de vectores."""
        metadata = {k: getattr(self, k) for k in ("destination_id", "destination", "section", "source")}
        return Document(page_content=self.embedding_text, metadata={"chunk_id": self.id, **metadata})


# "Cómo moverse" → "como-moverse", para el id del fragmento.
def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", strip_accents(text)).strip("-")


# Divide el Markdown por títulos y deja el título (#) y la sección (##) en los metadatos.
_by_heading = MarkdownHeaderTextSplitter(headers_to_split_on=[("#", "title"), ("##", "section")])


def _splitter(max_chars: int) -> RecursiveCharacterTextSplitter:
    # Corta por final de frase (y, si una frase no cabe, por espacios); el solapamiento
    # repite el final de un trozo al principio del siguiente.
    return RecursiveCharacterTextSplitter(
        chunk_size=max_chars,
        chunk_overlap=max_chars // 4,
        separators=[r"(?<=[.!?])\s+", r"\s+"],
        is_separator_regex=True,
        keep_separator="end",
    )


# Una guía → sus fragmentos.
def chunk_guide(markdown: str, destination_id: str, source: str, max_chars: int = MAX_CHARS) -> list[Chunk]:
    splitter = _splitter(max_chars)
    chunks: list[Chunk] = []
    for part in _by_heading.split_text(markdown):
        section = part.metadata.get("section")
        if not section:  # la introducción, antes de la primera sección
            continue
        destination = re.sub(r"^Guía práctica de\s+", "", part.metadata.get("title", destination_id))
        # Párrafos y saltos de línea en un solo texto con espacios simples.
        text = " ".join(part.page_content.split())
        for n, piece in enumerate(splitter.split_text(text)):
            chunks.append(Chunk(f"{destination_id}#{_slug(section)}#{n}", destination_id, destination, section, piece, source))
    return chunks


# Todas las guías → todos los fragmentos (84 con las 10 guías actuales).
def load_chunks(guides_dir: Path = GUIDES_DIR) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(guides_dir.glob("*.md")):
        chunks.extend(chunk_guide(path.read_text(encoding="utf-8"), path.stem, f"guides/{path.name}"))
    return chunks
