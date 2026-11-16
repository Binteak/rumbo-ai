import json

import pytest
from langchain_core.messages import ToolMessage

from app.agent import SYSTEM_PROMPT, Agent, RunStats, ToolContext
from app.agent.demo import parse_request
from tests.fakes import end_turn, provider, tool_turn


def run(agent, history, prompt, ctx=None):
    stats = RunStats()
    ctx = ctx or ToolContext(save_trip=lambda d: {**d, "id": 1})
    events = list(agent.run(history, prompt, ctx, stats))
    return events, stats


def test_tool_error_is_sent_back_and_model_recovers():
    p = provider(
        [
            tool_turn("get_climate", {"destination_id": "atlantida", "month": 5}),
            tool_turn("get_climate", {"destination_id": "kioto", "month": 5}, "t2"),
            end_turn("Hace buen tiempo."),
        ]
    )
    history = []
    events, stats = run(Agent([p]), history, "¿Qué tiempo hace?")
    results = [e for e in events if e["type"] == "tool_result"]
    assert results[0]["is_error"] and not results[1]["is_error"]
    # El segundo paso del modelo recibió el error como resultado de la herramienta.
    sent = p.llm.calls[1][-1]
    assert isinstance(sent, ToolMessage) and sent.status == "error" and "Ids válidos" in sent.text
    assert stats.status == "completed" and stats.tool_errors == 1 and stats.iterations == 3
    assert stats.input_tokens == 30 and stats.output_tokens == 15
    assert events[-1] == {"type": "final", "text": "Hace buen tiempo."}
    assert len(history) == 6  # usuario, modelo, resultado, modelo, resultado, modelo


def test_invalid_arguments_go_back_to_the_model():
    p = provider([tool_turn("get_climate", {"destination_id": "kioto", "month": 13}), end_turn("Perdona.")])
    events, stats = run(Agent([p]), [], "clima")
    result = next(e for e in events if e["type"] == "tool_result")
    assert result["is_error"] and "month" in json.dumps(result["output"])
    assert stats.status == "completed"


def test_model_receives_compact_tool_results_and_the_ui_the_full_ones():
    p = provider([tool_turn("build_itinerary", {"destination_id": "kioto", "days": 3}), end_turn("Listo.")])
    events, _ = run(Agent([p]), [], "3 días en Kioto")
    sent = json.loads(p.llm.calls[1][-1].text)
    assert set(sent) == {"destination", "days"} and isinstance(sent["days"][0]["plan"][0], str)
    full = next(e for e in events if e["type"] == "tool_result")["output"]
    assert "activities" in full["days"][0]


def test_max_iterations_stops_infinite_loops():
    p = provider([tool_turn("get_climate", {"destination_id": "kioto", "month": 1}, f"t{i}") for i in range(5)])
    events, stats = run(Agent([p], max_iterations=3), [], "bucle")
    assert stats.status == "max_iterations"
    assert events[-1]["type"] == "final"


def test_failing_model_falls_back_to_demo_and_keeps_history():
    history = []
    run(Agent([]), history, "3 días en Lisboa")  # turno correcto en modo demo
    saved = list(history)
    events, stats = run(Agent([provider([RuntimeError("API caída")])]), history, "otra")
    # El modelo real falla, pero la cadena acaba en el demo: el turno no se pierde.
    assert stats.status == "completed" and any(e["type"] == "notice" for e in events)
    assert len(history) > len(saved)


def test_old_history_format_is_discarded():
    history = [{"role": "user", "content": "hola"}]  # formato anterior a LangChain
    _, stats = run(Agent([]), history, "3 días en Lisboa")
    assert stats.status == "completed" and history[0]["type"] == "human"


def test_parse_request_understands_spanish():
    req = parse_request(["Una semana en Kioto en abril con mi pareja, lujo, nos encanta comer y los templos"])
    assert (req.destination_id, req.days, req.month, req.travelers, req.style) == ("kioto", 7, 4, 2, "lujo")
    assert {"gastronomia", "historia"} <= set(req.interests)


def test_demo_agent_completes_full_plan():
    saved = []
    ctx = ToolContext(save_trip=lambda d: saved.append(d) or {**d, "id": 1})
    events, stats = run(Agent([]), [], "Sorpréndeme: 3 días en mayo, playa y naturaleza, barato", ctx)
    tools = [e["name"] for e in events if e["type"] == "tool_call"]
    assert tools == ["search_destinations", "get_climate", "estimate_budget", "build_itinerary", "save_trip"]
    assert stats.status == "completed" and saved and saved[0]["style"] == "mochilero"


def test_server_saves_the_trip_when_the_model_forgets():
    p = provider(
        [
            tool_turn("estimate_budget", {"destination_id": "kioto", "days": 5, "travelers": 2, "style": "confort"}),
            tool_turn("get_climate", {"destination_id": "kioto", "month": 4}, "t2"),
            tool_turn("build_itinerary", {"destination_id": "kioto", "days": 5, "interests": ["historia"]}, "t3"),
            end_turn("Aquí tienes tu plan."),  # termina sin llamar a save_trip
        ]
    )
    saved = []
    ctx = ToolContext(save_trip=lambda d: saved.append(d) or {**d, "id": 3})
    events, stats = run(Agent([p]), [], "5 días en Kioto en abril", ctx)
    auto = [e for e in events if e["type"] == "tool_call" and e["id"] == "auto_save_trip"]
    assert auto and auto[0]["input"]["title"] == "5 días en Kioto en abril"
    assert saved[0]["travelers"] == 2 and len(saved[0]["itinerary"]) == 5 and saved[0]["climate"]["month"] == "abril"
    assert events[-1]["type"] == "final" and stats.status == "completed"


def test_no_auto_save_for_practical_questions():
    p = provider([tool_turn("search_travel_guides", {"query": "visado Japón"}), end_turn("Sin visado.")])
    saved = []
    events, _ = run(Agent([p]), [], "¿visado?", ToolContext(save_trip=lambda d: saved.append(d) or {**d, "id": 1}))
    assert saved == [] and not any(e.get("id") == "auto_save_trip" for e in events)


@pytest.mark.parametrize("question", ["¿Quién juega hoy al fútbol?", "¿Qué es mejor, el Barça o el Madrid?", "Escribe un poema"])
def test_demo_refuses_off_topic_questions(question):
    events, stats = run(Agent([]), [], question)
    assert not [e for e in events if e["type"] == "tool_call"]
    assert "Solo puedo ayudarte con viajes" in events[-1]["text"] and stats.status == "completed"


def test_demo_still_handles_follow_ups_after_a_plan():
    history = []
    ctx = ToolContext(save_trip=lambda d: {**d, "id": 1})
    run(Agent([]), history, "3 días en Lisboa en mayo", ctx)
    events, _ = run(Agent([]), history, "sí, hazlo más económico", ctx)
    assert "save_trip" in [e["name"] for e in events if e["type"] == "tool_call"]


def test_system_prompt_limits_scope_to_travel():
    assert "solo ayudas con viajes" in SYSTEM_PROMPT and "no la respondas" in SYSTEM_PROMPT
