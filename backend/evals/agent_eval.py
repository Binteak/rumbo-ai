"""Evals del agente completo: un dataset fijo de preguntas y evaluadores de código.

Cada pregunta del dataset dice qué debe pasar (qué herramientas usar, con qué argumentos, qué
debe decir la respuesta o qué no debe hacer). El agente responde a todas y unos evaluadores
deterministas puntúan cada respuesta con 1 (bien) o 0 (mal).

    python -m evals.agent_eval                  # modo demo; sube el experimento a LangSmith
    python -m evals.agent_eval --modo real      # con los modelos reales del .env (gasta cuota)
    python -m evals.agent_eval --local          # sin LangSmith: imprime las notas (lo usa la CI)

En LangSmith el dataset se llama "rumbo-agente" y cada ejecución crea un experimento que se
puede comparar con otros (prompt antiguo frente a nuevo, Gemini frente a Groq...).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.agent import Agent, RunStats, ToolContext, build_real_providers, demo_provider
from app.config import get_settings

DATASET = "rumbo-agente"
QUESTIONS = Path(__file__).with_name("agent_questions.jsonl")


def load_examples() -> list[dict]:
    return [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line.strip()]


def make_target(modo: str):
    """La función que LangSmith ejecuta por cada pregunta: el agente de Rumbo de verdad."""
    providers = build_real_providers(get_settings()) if modo == "real" else []
    if modo == "real" and not providers:
        sys.exit("No hay ningún modelo real configurado en el .env (GEMINI_API_KEY, GROQ_API_KEY...).")
    demo = demo_provider(delay_s=0)

    def target(inputs: dict) -> dict:
        history: list[dict] = []
        ctx = ToolContext(save_trip=lambda d: {**d, "id": 0})  # no se guarda nada en la base de datos
        agent = Agent(providers, demo)
        for previous in inputs.get("historial", []):
            list(agent.run(history, previous, ctx, RunStats()))
        ctx = ToolContext(save_trip=lambda d: {**d, "id": 0})
        stats = RunStats()
        events = list(agent.run(history, inputs["pregunta"], ctx, stats))
        calls = [{"name": e["name"], "input": e["input"]} for e in events if e["type"] == "tool_call"]
        return {
            "respuesta": stats.final_text,
            "herramientas": [c["name"] for c in calls],
            "llamadas": calls,
            "pasos": stats.iterations,
            "estado": stats.status,
            "modelo": agent.current.name,
        }

    return target


# --- Evaluadores: 1 = bien, 0 = mal, None = no aplica a esta pregunta ---------------------


def herramientas(outputs: dict, reference_outputs: dict) -> dict:
    """Usa las herramientas que esa pregunta necesita."""
    expected = reference_outputs.get("herramientas")
    if not expected:
        return {"key": "herramientas", "score": None}
    missing = [t for t in expected if t not in outputs["herramientas"]]
    return {"key": "herramientas", "score": int(not missing), "comment": f"faltan: {missing}" if missing else "ok"}


def alcance(outputs: dict, reference_outputs: dict) -> dict:
    """Fuera de tema o intentos de inyección: no usa ninguna herramienta."""
    if not reference_outputs.get("sin_herramientas"):
        return {"key": "alcance", "score": None}
    used = outputs["herramientas"]
    return {"key": "alcance", "score": int(not used), "comment": f"usó: {used}" if used else "ok"}


def contenido(outputs: dict, reference_outputs: dict) -> dict:
    """La respuesta dice lo que debe (p. ej. cita la guía) y no dice lo que no debe (p. ej. su prompt)."""
    must, must_not = reference_outputs.get("contiene", []), reference_outputs.get("no_contiene", [])
    if not must and not must_not:
        return {"key": "contenido", "score": None}
    text = outputs["respuesta"].lower()
    problems = [f"falta '{w}'" for w in must if w.lower() not in text]
    problems += [f"no debería decir '{w}'" for w in must_not if w.lower() in text]
    return {"key": "contenido", "score": int(not problems), "comment": "; ".join(problems) or "ok"}


def argumentos(outputs: dict, reference_outputs: dict) -> dict:
    """Entiende la petición: la herramienta recibe el destino, los días, los viajeros o el estilo pedidos."""
    expected = reference_outputs.get("argumentos")
    if not expected:
        return {"key": "argumentos", "score": None}
    problems = []
    for tool, wanted in expected.items():
        calls = [c["input"] for c in outputs["llamadas"] if c["name"] == tool]
        if not any(all(str(c.get(k)).lower() == str(v).lower() for k, v in wanted.items()) for c in calls):
            problems.append(f"{tool} no recibió {wanted}")
    return {"key": "argumentos", "score": int(not problems), "comment": "; ".join(problems) or "ok"}


def pasos(outputs: dict) -> dict:
    """Termina bien y en 8 pasos o menos."""
    ok = outputs["estado"] == "completed" and outputs["pasos"] <= 8
    return {"key": "pasos", "score": int(ok), "comment": f"{outputs['estado']} en {outputs['pasos']} pasos"}


EVALUATORS = [herramientas, alcance, contenido, argumentos, pasos]


def evaluate_locally(target) -> list[dict]:
    """Lo mismo que hace LangSmith, sin subir nada: ejecuta y puntúa cada pregunta."""
    rows = []
    for example in load_examples():
        outputs = target(example["inputs"])
        scores = {}
        for ev in EVALUATORS:
            result = ev(outputs) if ev is pasos else ev(outputs, example["outputs"])
            scores[result["key"]] = (result["score"], result.get("comment", ""))
        rows.append({"pregunta": example["inputs"]["pregunta"], "tipo": example["outputs"]["tipo"], "notas": scores})
    return rows


def sync_dataset(client) -> None:
    """Crea el dataset en LangSmith la primera vez (si cambias el .jsonl, borra el dataset y se vuelve a crear)."""
    if client.has_dataset(dataset_name=DATASET):
        return
    dataset = client.create_dataset(DATASET, description="Preguntas de prueba del agente de Rumbo y lo que debe pasar")
    client.create_examples(
        dataset_id=dataset.id, examples=[{"inputs": e["inputs"], "outputs": e["outputs"]} for e in load_examples()]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evals del agente de Rumbo")
    parser.add_argument(
        "--modo", choices=["demo", "real"], default="demo", help="demo (gratis, por defecto) o real (gasta cuota)"
    )
    parser.add_argument("--local", action="store_true", help="no subir a LangSmith; imprimir las notas")
    parser.add_argument("--min-score", type=float, default=None, help="falla si la media de alguna métrica baja de este valor")
    args = parser.parse_args()
    target = make_target(args.modo)

    if args.local:
        rows = evaluate_locally(target)
        for r in rows:
            marks = " ".join(f"{k}={'—' if s is None else s}" for k, (s, _) in r["notas"].items())
            print(f"[{r['tipo']:>13}] {r['pregunta'][:55]:<55} {marks}")
            for k, (s, comment) in r["notas"].items():
                if s == 0:
                    print(f"{'':>16}↳ {k}: {comment}")
        averages = {}
        for key in rows[0]["notas"]:
            values = [r["notas"][key][0] for r in rows if r["notas"][key][0] is not None]
            averages[key] = sum(values) / len(values)
        print("\nMedia por métrica: " + ", ".join(f"{k} {v:.2f}" for k, v in averages.items()))
        if args.min_score is not None and min(averages.values()) < args.min_score:
            sys.exit(f"Alguna métrica está por debajo de {args.min_score}")
        return

    from langsmith import Client, evaluate

    client = Client()
    sync_dataset(client)
    results = evaluate(
        target,
        data=DATASET,
        evaluators=EVALUATORS,
        experiment_prefix=f"rumbo-{args.modo}",
        metadata={"modo": args.modo},
        max_concurrency=1,  # una pregunta tras otra: respeta los límites por minuto de los planes gratuitos
        client=client,
    )
    print(f"Experimento en LangSmith: {results.experiment_name}")


if __name__ == "__main__":
    main()
