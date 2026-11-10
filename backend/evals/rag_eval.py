"""Evaluación de la recuperación del RAG.

Mide si, para cada pregunta de `rag_questions.jsonl`, el fragmento correcto de la guía
aparece entre los resultados. Dos escenarios:

- filtered: con el destino indicado, como hace el agente cuando ya sabe de qué ciudad se habla.
- open: sin destino; el retriever tiene que deducirlo o buscar en todas las guías.

Métricas: hit@1 (el primero es el correcto), recall@k (está entre los k primeros) y MRR
(media de 1/posición). Sale con código 1 si recall@k baja del mínimo, así la CI falla
cuando un cambio en las guías o en el retriever empeora la búsqueda.

    python -m evals.rag_eval                     # embedder local, sin coste
    python -m evals.rag_eval --embedder voyage   # con VOYAGE_API_KEY
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
from app.rag.store import MemoryVectorStore

QUESTIONS = Path(__file__).with_name("rag_questions.jsonl")


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--k", type=int, default=4)
    parser.add_argument("--embedder", choices=["hashing", "voyage"], default="hashing")
    parser.add_argument("--min-recall", type=float, default=0.9, help="recall@k mínimo en el escenario filtered")
    args = parser.parse_args()

    embedder = VoyageEmbedder(os.environ["VOYAGE_API_KEY"]) if args.embedder == "voyage" else HashingEmbedder()
    chunks = load_chunks()
    store = MemoryVectorStore()
    ingest(chunks, embedder, store)
    from app.rag import _destination_aliases

    retriever = Retriever(chunks, embedder, store, _destination_aliases())
    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]

    report = {
        "embedder": embedder.name,
        "filtered": evaluate(retriever, questions, args.k, use_filter=True),
        "open": evaluate(retriever, questions, args.k, use_filter=False),
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))

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
