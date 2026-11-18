"""Evaluación de la recuperación del RAG.

Mide si, para cada pregunta de `rag_questions.jsonl`, el fragmento correcto de la guía
aparece entre los resultados. Dos escenarios:

- filtered: con el destino indicado, como hace el agente cuando ya sabe de qué ciudad se habla.
- open: sin destino; el retriever tiene que deducirlo o buscar en todas las guías.

Métricas: hit@1 (el primero es el correcto), recall@k (está entre los k primeros) y MRR
(media de 1/posición). Sale con código 1 si recall@k baja del mínimo, así la CI falla
cuando un cambio en las guías o en el retriever empeora la búsqueda.

    python -m evals.rag_eval                     # embedder local, sin coste (lo usa la CI)
    python -m evals.rag_eval --embedder voyage   # con VOYAGE_API_KEY
    python -m evals.rag_eval --langsmith         # además sube el dataset "rumbo-rag" y dos experimentos a LangSmith

En LangSmith cada ejecución crea un experimento por escenario (filtered y open) con las mismas
métricas por pregunta, para comparar versiones del retriever (otro embedder, otro k de RRF...).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from app.rag.chunking import load_chunks
from app.rag.embeddings import HashingEmbedder, VoyageEmbedder
from app.rag.ingest import ingest
from app.rag.retriever import Retriever
from app.rag.store import build_memory_store

QUESTIONS = Path(__file__).with_name("rag_questions.jsonl")
DATASET = "rumbo-rag"


def evaluate(retriever: Retriever, questions: list[dict], k: int, use_filter: bool) -> dict:
    hits1 = hitsk = 0
    rr = 0.0
    failures = []
    for item in questions:
        result = retriever.search(item["q"], k=k, destination_id=item["destination_id"] if use_filter else None)
        ids = [h.chunk.id.rsplit("#", 1)[0] for h in result.hits]
        rank = ids.index(item["expected"]) + 1 if item["expected"] in ids else None
        hits1 += rank == 1
        hitsk += rank is not None
        rr += 1 / rank if rank else 0
        if rank != 1:
            failures.append({"q": item["q"], "expected": item["expected"], "got": ids[:3], "rank": rank})
    n = len(questions)
    return {"n": n, "hit@1": round(hits1 / n, 3), f"recall@{k}": round(hitsk / n, 3), "mrr": round(rr / n, 3), "misses": failures}


# --- LangSmith: mismas métricas, una puntuación por pregunta -------------------------------


def make_target(retriever: Retriever, k: int, use_filter: bool):
    """La función que LangSmith ejecuta por cada pregunta: el retriever del RAG."""

    def target(inputs: dict) -> dict:
        destination_id = inputs["destination_id"] if use_filter else None
        hits = retriever.search(inputs["pregunta"], k=k, destination_id=destination_id).hits
        return {"secciones": [h.chunk.id.rsplit("#", 1)[0] for h in hits]}

    return target


def _rank(outputs: dict, reference_outputs: dict) -> int | None:
    """Posición de la sección esperada entre las recuperadas (1 = primera), o None si no está."""
    found, expected = outputs["secciones"], reference_outputs["seccion"]
    return found.index(expected) + 1 if expected in found else None


def hit_at_1(outputs: dict, reference_outputs: dict) -> dict:
    """La primera sección recuperada es la correcta."""
    rank = _rank(outputs, reference_outputs)
    return {"key": "hit@1", "score": int(rank == 1), "comment": f"posición {rank}"}


def recall_at_k(outputs: dict, reference_outputs: dict) -> dict:
    """La sección correcta está entre las recuperadas."""
    rank = _rank(outputs, reference_outputs)
    return {"key": "recall@k", "score": int(rank is not None), "comment": f"posición {rank}"}


def reciprocal_rank(outputs: dict, reference_outputs: dict) -> dict:
    """1 / posición de la sección correcta (0 si no está); su media es el MRR."""
    rank = _rank(outputs, reference_outputs)
    return {"key": "mrr", "score": 1 / rank if rank else 0.0}


LANGSMITH_EVALUATORS = [hit_at_1, recall_at_k, reciprocal_rank]


def sync_dataset(client, questions: list[dict]) -> None:
    """Crea el dataset en LangSmith la primera vez (si cambias el .jsonl, borra el dataset y se vuelve a crear)."""
    if client.has_dataset(dataset_name=DATASET):
        return
    dataset = client.create_dataset(DATASET, description="Preguntas de recuperación del RAG de Rumbo y la sección esperada")
    client.create_examples(
        dataset_id=dataset.id,
        examples=[
            {"inputs": {"pregunta": q["q"], "destination_id": q["destination_id"]}, "outputs": {"seccion": q["expected"]}}
            for q in questions
        ],
    )


def run_in_langsmith(retriever: Retriever, questions: list[dict], k: int, embedder_name: str, client=None) -> list[str]:
    """Sube el dataset (si falta) y lanza un experimento por escenario. Devuelve los nombres de los experimentos."""
    from langsmith import Client
    from langsmith import evaluate as ls_evaluate

    client = client or Client()
    sync_dataset(client, questions)
    names = []
    for scenario, use_filter in (("filtered", True), ("open", False)):
        results = ls_evaluate(
            make_target(retriever, k, use_filter),
            data=DATASET,
            evaluators=LANGSMITH_EVALUATORS,
            experiment_prefix=f"rag-{embedder_name}-{scenario}",
            metadata={"embedder": embedder_name, "escenario": scenario, "k": k},
            client=client,
        )
        names.append(results.experiment_name)
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--embedder", choices=["hashing", "voyage"], default="hashing")
    parser.add_argument("--min-recall", type=float, default=0.9, help="recall@k mínimo en el escenario filtered")
    parser.add_argument("--langsmith", action="store_true", help="subir también el dataset y los experimentos a LangSmith")
    args = parser.parse_args()

    embedder = VoyageEmbedder(os.environ["VOYAGE_API_KEY"]) if args.embedder == "voyage" else HashingEmbedder()
    chunks = load_chunks()
    store, records = build_memory_store(embedder)
    ingest(chunks, store, records)
    from app.rag import _destination_aliases

    retriever = Retriever(chunks, embedder, store, _destination_aliases())
    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]

    report = {
        "embedder": embedder.name,
        "filtered": evaluate(retriever, questions, args.k, use_filter=True),
        "open": evaluate(retriever, questions, args.k, use_filter=False),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.langsmith:
        for name in run_in_langsmith(retriever, questions, args.k, embedder.name):
            print(f"Experimento en LangSmith: {name}", file=sys.stderr)

    recall = report["filtered"][f"recall@{args.k}"]
    if summary := os.getenv("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### Evals RAG ({embedder.name}, {len(questions)} preguntas)\n\n")
            f.write(f"| Escenario | hit@1 | recall@{args.k} | MRR |\n|---|---|---|---|\n")
            for name in ("filtered", "open"):
                r = report[name]
                f.write(f"| {name} | {r['hit@1']} | {r[f'recall@{args.k}']} | {r['mrr']} |\n")
    if recall < args.min_recall:
        print(f"\nrecall@{args.k} = {recall} < {args.min_recall}: la recuperación ha empeorado", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
