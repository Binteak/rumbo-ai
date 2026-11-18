import json

import pytest

from app.rag import _destination_aliases
from app.rag.chunking import load_chunks
from app.rag.embeddings import HashingEmbedder
from app.rag.ingest import ingest
from app.rag.retriever import Retriever
from app.rag.store import build_memory_store
from evals.rag_eval import (
    DATASET,
    LANGSMITH_EVALUATORS,
    QUESTIONS,
    evaluate,
    hit_at_1,
    make_target,
    recall_at_k,
    reciprocal_rank,
    sync_dataset,
)


@pytest.fixture(scope="module")
def retriever():
    chunks, embedder = load_chunks(), HashingEmbedder()
    store, records = build_memory_store(embedder)
    ingest(chunks, store, records)
    return Retriever(chunks, embedder, store, _destination_aliases())


@pytest.fixture(scope="module")
def questions():
    return [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_evaluators_score_by_position():
    found = {"secciones": ["kioto#a", "kioto#b"]}
    assert hit_at_1(found, {"seccion": "kioto#a"})["score"] == 1
    assert hit_at_1(found, {"seccion": "kioto#b"})["score"] == 0
    assert recall_at_k(found, {"seccion": "kioto#b"})["score"] == 1
    assert recall_at_k(found, {"seccion": "kioto#c"})["score"] == 0
    assert reciprocal_rank(found, {"seccion": "kioto#b"})["score"] == 0.5
    assert reciprocal_rank(found, {"seccion": "kioto#c"})["score"] == 0.0


@pytest.mark.parametrize("use_filter", [True, False])
def test_langsmith_evaluators_match_the_ci_report(retriever, questions, use_filter):
    """Lo que se sube a LangSmith da las mismas medias que el informe de la CI."""
    report = evaluate(retriever, questions, k=4, use_filter=use_filter)
    target = make_target(retriever, 4, use_filter)
    scores = {ev.__name__: [] for ev in LANGSMITH_EVALUATORS}
    for q in questions:
        outputs = target({"pregunta": q["q"], "destination_id": q["destination_id"]})
        for ev in LANGSMITH_EVALUATORS:
            scores[ev.__name__].append(ev(outputs, {"seccion": q["expected"]})["score"])
    mean = {name: round(sum(v) / len(v), 3) for name, v in scores.items()}
    assert mean["hit_at_1"] == report["hit@1"]
    assert mean["recall_at_k"] == report["recall@4"]
    assert mean["reciprocal_rank"] == report["mrr"]


class FakeClient:
    def __init__(self, exists: bool) -> None:
        self.exists, self.created = exists, []

    def has_dataset(self, dataset_name):
        return self.exists

    def create_dataset(self, name, description):
        self.name = name
        return type("Dataset", (), {"id": "ds-1"})()

    def create_examples(self, dataset_id, examples):
        self.created = examples


def test_sync_dataset_uploads_questions_once(questions):
    client = FakeClient(exists=False)
    sync_dataset(client, questions)
    assert client.name == DATASET and len(client.created) == len(questions)
    first = client.created[0]
    assert set(first["inputs"]) == {"pregunta", "destination_id"} and set(first["outputs"]) == {"seccion"}

    again = FakeClient(exists=True)
    sync_dataset(again, questions)
    assert again.created == []
