from app.agent import Agent, RunStats, ToolContext
from app.agent.demo import DemoProvider, parse_request
from app.agent.providers import Block, ModelTurn


class ScriptedProvider:
    """Proveedor falso: devuelve turnos predefinidos y guarda lo que recibe."""

    name, model = "fake", "fake-model"

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def complete(self, system, tools, messages):
        self.calls.append([*messages])
        return self.turns.pop(0)


def tool_turn(name, args, tid="t1"):
    block = Block(type="tool_use", id=tid, name=name, input=args)
    return ModelTurn("tool_use", [block], [{"type": "tool_use", "id": tid, "name": name, "input": args}], 10, 5)


def end_turn(text):
    return ModelTurn("end_turn", [Block(type="text", text=text)], [{"type": "text", "text": text}], 10, 5)


def run(agent, history, prompt, ctx=None):
    stats = RunStats()
    events = list(agent.run(history, prompt, ctx or ToolContext(), stats))
    return events, stats


def test_tool_error_is_sent_back_and_model_recovers():
    provider = ScriptedProvider(
        [
            tool_turn("get_climate", {"destination_id": "atlantida", "month": 5}),
            tool_turn("get_climate", {"destination_id": "kioto", "month": 5}, "t2"),
            end_turn("Hace buen tiempo."),
        ]
    )
    history = []
    events, stats = run(Agent(provider), history, "¿Qué tiempo hace?")
    results = [e for e in events if e["type"] == "tool_result"]
    assert results[0]["is_error"] and not results[1]["is_error"]
    # El segundo turno recibió el error como tool_result con is_error.
    sent = provider.calls[1][-1]["content"][0]
    assert sent["is_error"] is True and "Ids válidos" in sent["content"]
    assert stats.status == "completed" and stats.tool_errors == 1
    assert stats.input_tokens == 30 and stats.output_tokens == 15
    assert len(history) == 6  # user, assistant, results, assistant, results, assistant


def test_max_iterations_stops_infinite_loops():
    provider = ScriptedProvider([tool_turn("get_climate", {"destination_id": "kioto", "month": 1}, f"t{i}") for i in range(5)])
    events, stats = run(Agent(provider, max_iterations=3), [], "bucle")
    assert stats.status == "max_iterations"
    assert events[-1]["type"] == "final"


def test_history_is_untouched_when_provider_fails():
    class Boom:
        name, model = "boom", "boom"

        def complete(self, *a):
            raise RuntimeError("API caída")

    history = [{"role": "user", "content": "hola"}]
    events, stats = run(Agent(Boom()), history, "otra")
    assert events[-1] == {"type": "error", "message": "RuntimeError: API caída"}
    assert stats.status == "error"
    assert history == [{"role": "user", "content": "hola"}]


def test_parse_request_understands_spanish():
    req = parse_request(["Una semana en Kioto en abril con mi pareja, lujo, nos encanta comer y los templos"])
    assert (req.destination_id, req.days, req.month, req.travelers, req.style) == ("kioto", 7, 4, 2, "lujo")
    assert {"gastronomia", "historia"} <= set(req.interests)


def test_demo_agent_completes_full_plan():
    saved = []
    ctx = ToolContext(save_trip=lambda d: saved.append(d) or {**d, "id": 1})
    events, stats = run(Agent(DemoProvider()), [], "Sorpréndeme: 3 días en mayo, playa y naturaleza, barato", ctx)
    tools = [e["name"] for e in events if e["type"] == "tool_call"]
    assert tools == ["search_destinations", "get_climate", "estimate_budget", "build_itinerary", "save_trip"]
    assert stats.status == "completed" and saved and saved[0]["style"] == "mochilero"


def test_server_saves_the_trip_when_the_model_forgets():
    provider = ScriptedProvider(
        [
            tool_turn("estimate_budget", {"destination_id": "kioto", "days": 5, "travelers": 2, "style": "confort"}),
            tool_turn("get_climate", {"destination_id": "kioto", "month": 4}, "t2"),
            tool_turn("build_itinerary", {"destination_id": "kioto", "days": 5, "interests": ["historia"]}, "t3"),
            end_turn("Aquí tienes tu plan."),  # termina sin llamar a save_trip
        ]
    )
    saved = []
    ctx = ToolContext(save_trip=lambda d: saved.append(d) or {**d, "id": 3})
    events, stats = run(Agent(provider), [], "5 días en Kioto en abril", ctx)
    auto = [e for e in events if e["type"] == "tool_call" and e["id"] == "auto_save_trip"]
    assert auto and auto[0]["input"]["title"] == "5 días en Kioto en abril"
    assert saved[0]["travelers"] == 2 and len(saved[0]["itinerary"]) == 5 and saved[0]["climate"]["month"] == "abril"
    assert events[-1]["type"] == "final" and stats.status == "completed"


def test_no_auto_save_for_practical_questions():
    provider = ScriptedProvider([tool_turn("search_travel_guides", {"query": "visado Japón"}), end_turn("Sin visado.")])
    saved = []
    events, _ = run(Agent(provider), [], "¿visado?", ToolContext(save_trip=lambda d: saved.append(d) or {**d, "id": 1}))
    assert saved == [] and not any(e.get("id") == "auto_save_trip" for e in events)
