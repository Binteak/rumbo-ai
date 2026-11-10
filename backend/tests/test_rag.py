import json
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agent import Agent, RunStats, ToolContext
from app.agent.demo import DemoProvider
from app.agent.tools import ToolError, destinations, execute_tool
from app.main import app
from app.rag import get_rag
from app.rag.chunking import chunk_guide, load_chunks
from app.rag.embeddings import HashingEmbedder, VoyageEmbedder
from app.rag.ingest import ingest
from app.rag.retriever import Retriever
from app.rag.store import MemoryVectorStore
from app.rag.text import expand_query, tokenize

# --- Chunking -------------------------------------------------------------------


def test_every_destination_has_a_guide_split_by_sections():
    chunks = load_chunks()
    assert {c.destination_id for c in chunks} == set(destinations())
    assert len({c.id for c in chunks}) == len(chunks)
    kioto = [c for c in chunks if c.destination_id == "kioto"]
    assert {"Documentación y entrada", "Cómo moverse", "Dinero y propinas"} <= {c.section for c in kioto}
    assert all(c.source == "guides/kioto.md" and c.destination == "Kioto" for c in kioto)


def test_long_sections_are_split_with_overlap():
    sentences = [f"Frase número {i} con bastante texto de relleno para la prueba." for i in range(30)]
    chunks = chunk_guide("# Guía práctica de Test\n\n## Larga\n\n" + " ".join(sentences), "test", "guides/test.md", max_chars=300)
    assert len(chunks) > 1
    assert all(len(c.text) <= 300 for c in chunks)
    last_sentence = chunks[0].text.split(". ")[-1]
    assert chunks[1].text.startswith(last_sentence.rstrip("."))  # solapamiento de una frase


def test_tokenize_unifies_accents_plural_and_gender():
    assert tokenize("Visados") == tokenize("visado")
    assert tokenize("Enchufes") == tokenize("enchufe")
    assert tokenize("¿Cómo?") == tokenize("como")


def test_query_expansion_maps_user_words_to_guide_sections():
    _, added = expand_query("¿cómo me muevo y dónde duermo?")
    assert "como moverse transporte metro aeropuerto" in added
    assert "donde alojarse barrio" in added


# --- Embeddings -----------------------------------------------------------------


def test_hashing_embedder_is_deterministic_and_normalized():
    emb = HashingEmbedder(dim=64)
    a, b = emb.embed_query("visado Japón"), emb.embed_query("visado Japón")
    assert a == b and len(a) == 64
    assert abs(sum(v * v for v in a) - 1) < 1e-9


def test_voyage_embedder_sends_input_type_and_keeps_order():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append((request.url.host, body["input_type"], body["model"]))
        data = [{"index": i, "embedding": [float(i), 1.0]} for i in range(len(body["input"]))]
        return httpx.Response(200, json={"data": list(reversed(data))})

    emb = VoyageEmbedder("pa-test", "voyage-4-lite", transport=httpx.MockTransport(handler))
    assert emb.embed_documents(["a", "b", "c"]) == [[0.0, 1.0], [1.0, 1.0], [2.0, 1.0]]
    assert emb.embed_query("hola") == [0.0, 1.0]
    assert seen == [("api.voyageai.com", "document", "voyage-4-lite"), ("api.voyageai.com", "query", "voyage-4-lite")]
    atlas = VoyageEmbedder("al-test", transport=httpx.MockTransport(handler))
    assert atlas.client.base_url.host == "ai.mongodb.com"


# --- Ingesta y recuperación -----------------------------------------------------


@pytest.fixture
def retriever():
    chunks = load_chunks()
    store = MemoryVectorStore()
    ingest(chunks, HashingEmbedder(), store)
    return Retriever(chunks, HashingEmbedder(), store, {"japon": "kioto", "Lisboa": "lisboa"})


def test_ingest_is_incremental():
    chunks = load_chunks()
    store, emb = MemoryVectorStore(), HashingEmbedder()
    assert ingest(chunks, emb, store).embedded == len(chunks)
    assert ingest(chunks, emb, store).embedded == 0  # sin cambios, no se recalcula nada
    stats = ingest(chunks[1:], emb, store)
    assert stats.embedded == 0 and stats.deleted == 1


def test_hybrid_search_finds_the_right_section(retriever):
    result = retriever.search("¿Necesito visado para Japón?")
    assert result.mode == "hybrid"
    assert result.destination_id == "kioto"  # detectado en la pregunta
    assert result.hits[0].chunk.id == "kioto#documentacion-y-entrada#0"
    top = result.hits[0].to_dict()
    assert top["match"]["bm25_rank"] == 1 and top["match"]["vector_rank"] is not None


def test_destination_filter_is_respected(retriever):
    hits = retriever.search("propinas", destination_id="lisboa").hits
    assert hits and all(h.chunk.destination_id == "lisboa" for h in hits)
    assert hits[0].chunk.section == "Dinero y propinas"


def test_off_topic_question_returns_nothing(retriever):
    assert retriever.search("receta de la paella valenciana").hits == []


def test_vector_failure_degrades_to_bm25(retriever):
    class Broken(HashingEmbedder):
        def embed_query(self, text):
            raise httpx.ConnectError("sin red")

    retriever.embedder = Broken()
    result = retriever.search("propinas en Lisboa")
    assert result.mode == "bm25"
    assert result.hits[0].chunk.id == "lisboa#dinero-y-propinas#0"


# --- Herramienta, agente y API --------------------------------------------------


def test_tool_returns_sources_and_grounding_instructions():
    out = execute_tool("search_travel_guides", {"query": "¿se deja propina?", "destination_id": "nuevayork"})
    assert out["results"][0]["section"] == "Dinero y propinas"
    assert out["results"][0]["source"] == "guides/nuevayork.md"
    assert "cita la fuente" in out["instructions"]
    empty = execute_tool("search_travel_guides", {"query": "receta de la paella valenciana"})
    assert empty["results"] == [] and "en lugar de inventar" in empty["instructions"]


def test_tool_rejects_unknown_destination():
    with pytest.raises(ToolError, match="Ids válidos"):
        execute_tool("search_travel_guides", {"query": "visado", "destination_id": "atlantida"})


def test_demo_answers_practical_questions_with_rag_only():
    events = list(Agent(DemoProvider()).run([], "¿Es seguro Marrakech de noche?", ToolContext(), RunStats()))
    assert [e["name"] for e in events if e["type"] == "tool_call"] == ["search_travel_guides"]
    assert "Fuente: Guía de Marrakech · Seguridad" in events[-1]["text"]


def test_demo_uses_conversation_context_for_follow_up_questions():
    saved = []
    agent, history = Agent(DemoProvider()), []
    ctx = ToolContext(save_trip=lambda d: saved.append(d) or {**d, "id": 1})
    list(agent.run(history, "3 días en Lisboa en mayo", ctx, RunStats()))
    events = list(agent.run(history, "¿y cómo me muevo por allí?", ctx, RunStats()))
    call = next(e for e in events if e["type"] == "tool_call")
    assert call["input"]["destination_id"] == "lisboa"
    assert "Guía de Lisboa · Cómo moverse" in events[-1]["text"]


def test_demo_does_not_loop_when_the_guides_fail(monkeypatch):
    import dataclasses

    import app.agent.tools as tools

    def boom(_args):
        raise ToolError("RAG caído")

    broken = dataclasses.replace(tools.TOOLS["search_travel_guides"], handler=boom)
    monkeypatch.setitem(tools.TOOLS, "search_travel_guides", broken)
    stats = RunStats()
    events = list(Agent(DemoProvider()).run([], "¿Necesito visado para Japón?", ToolContext(), stats))
    assert stats.status == "completed" and stats.tool_calls == 1 and stats.tool_errors == 1
    assert "no he podido consultar" in events[-1]["text"]


def test_rag_endpoints():
    with TestClient(app) as client:
        status = client.get("/api/rag/status").json()
        assert status["chunks"] > 50 and status["embedder"] == "hashing-512" and status["store"] == "memory"
        r = client.get("/api/rag/search", params={"q": "enchufes", "destination_id": "kioto"}).json()
        assert r["results"][0]["section"] == "Enchufes y conectividad"
        assert client.get("/api/rag/search", params={"q": "enchufes", "destination_id": "x"}).status_code == 404


def test_rag_singleton_is_reused():
    assert get_rag() is get_rag()


# --- PostgreSQL + pgvector (solo si hay una BD de prueba: en CI con un service container) ---


@pytest.mark.skipif(not os.getenv("TEST_PG_URL"), reason="TEST_PG_URL no definida")
def test_pgvector_store_round_trip():
    from sqlalchemy import create_engine, text

    from app.rag.store import PgVectorStore

    engine = create_engine(os.environ["TEST_PG_URL"])
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS rag_chunks"))
    store = PgVectorStore(engine)
    chunks, emb = load_chunks(), HashingEmbedder()
    assert ingest(chunks, emb, store).embedded == len(chunks)
    assert ingest(chunks, emb, store).embedded == 0
    hits = store.search(emb.name, emb.embed_query("Kioto · Enchufes y conectividad enchufe tipo A"), 3, "kioto")
    assert hits[0][0] == "kioto#enchufes-y-conectividad#0" and -1 <= hits[0][1] <= 1
    retriever = Retriever(chunks, emb, store)
    assert retriever.search("propinas", destination_id="lisboa").hits[0].chunk.section == "Dinero y propinas"
