import json

import fakeredis
import httpx
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.agent import Agent, DemoProvider, GuardedProvider, OpenAICompatibleProvider, RateLimited, RunStats, ToolContext
from app.agent.providers import Block, ModelTurn, to_openai_messages, to_openai_tools
from app.agent.tools import tool_schemas
from app.limits import LimitsConfig, MemoryCounterStore, RedisCounterStore, UsageLimits, client_ip

# --- Traducción al formato de OpenAI --------------------------------------------


def test_history_is_translated_to_openai_format():
    history = [
        {"role": "user", "content": "3 días en Lisboa"},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "...", "signature": "x"},
                {"type": "text", "text": "Calculo el presupuesto."},
                {"type": "tool_use", "id": "t1", "name": "estimate_budget", "input": {"destination_id": "lisboa", "days": 3}},
            ],
        },
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": '{"total_eur": 360}'}]},
    ]
    out = to_openai_messages("sistema", history)
    assert out[0] == {"role": "system", "content": "sistema"}
    assert out[1] == {"role": "user", "content": "3 días en Lisboa"}
    assert out[2]["content"] == "Calculo el presupuesto."  # el bloque de razonamiento de Claude se omite
    call = out[2]["tool_calls"][0]
    assert call["id"] == "t1" and json.loads(call["function"]["arguments"])["days"] == 3
    assert out[3] == {"role": "tool", "tool_call_id": "t1", "content": '{"total_eur": 360}'}


def test_tools_are_exposed_as_functions():
    tools = to_openai_tools(tool_schemas())
    assert {t["type"] for t in tools} == {"function"}
    climate = next(t["function"] for t in tools if t["function"]["name"] == "get_climate")
    assert climate["parameters"]["required"] == ["destination_id", "month"]


# --- Proveedor compatible con OpenAI (Groq) --------------------------------------


def completion(content=None, tool_calls=None, finish="stop", prompt=100, completion_tokens=20, cached=0):
    message = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {
        "choices": [{"message": message, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion_tokens,
            "prompt_tokens_details": {"cached_tokens": cached},
        },
    }


def tool_call(name, args, cid="call_1"):
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def provider_with(responses, seen=None):
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        return queue.pop(0)

    return OpenAICompatibleProvider("gsk-test", "openai/gpt-oss-120b", transport=httpx.MockTransport(handler))


def test_provider_parses_tool_calls_usage_and_sends_low_reasoning():
    seen = []
    p = provider_with(
        [
            httpx.Response(
                200,
                json=completion(
                    None, [tool_call("get_climate", {"destination_id": "kioto", "month": 4})], "tool_calls", cached=60
                ),
            )
        ],
        seen,
    )
    turn = p.complete("s", tool_schemas(), [{"role": "user", "content": "hola"}])
    assert turn.stop_reason == "tool_use"
    assert turn.blocks[0].name == "get_climate" and turn.blocks[0].input == {"destination_id": "kioto", "month": 4}
    assert (turn.input_tokens, turn.output_tokens, turn.cached_tokens) == (100, 20, 60)
    assert turn.history_content == [
        {"type": "tool_use", "id": "call_1", "name": "get_climate", "input": {"destination_id": "kioto", "month": 4}}
    ]
    assert seen[0]["reasoning_effort"] == "low" and seen[0]["tools"][0]["type"] == "function"


def test_provider_maps_finish_reasons_and_bad_json():
    p = provider_with(
        [
            httpx.Response(200, json=completion("cortado", finish="length")),
            httpx.Response(
                200,
                json=completion(
                    None, [{"id": "c", "type": "function", "function": {"name": "get_climate", "arguments": "{mal"}}]
                ),
            ),
        ]
    )
    assert p.complete("s", [], [{"role": "user", "content": "x"}]).stop_reason == "max_tokens"
    turn = p.complete("s", [], [{"role": "user", "content": "x"}])
    assert "_argumentos_no_validos" in turn.blocks[0].input  # Pydantic devolverá el error al modelo


def test_provider_raises_rate_limited_with_retry_after():
    p = provider_with(
        [
            httpx.Response(429, headers={"retry-after": "7"}, json={"error": {"message": "rate limit"}}),
            httpx.Response(429, text="Rate limit reached. Please try again in 6m11.5s."),
        ]
    )
    with pytest.raises(RateLimited) as e:
        p.complete("s", [], [{"role": "user", "content": "x"}])
    assert e.value.retry_after == 7
    with pytest.raises(RateLimited) as e:
        p.complete("s", [], [{"role": "user", "content": "x"}])
    assert e.value.retry_after == pytest.approx(371.5)


def test_provider_retries_once_on_malformed_tool_call():
    p = provider_with(
        [httpx.Response(400, json={"error": {"code": "tool_use_failed"}}), httpx.Response(200, json=completion("ok"))]
    )
    assert p.complete("s", [], [{"role": "user", "content": "x"}]).blocks[0].text == "ok"


def test_full_agent_run_with_openai_compatible_provider():
    seen = []
    p = provider_with(
        [
            httpx.Response(
                200, json=completion(None, [tool_call("get_climate", {"destination_id": "kioto", "month": 4})], "tool_calls")
            ),
            httpx.Response(200, json=completion("En abril hay 15 °C de media.")),
        ],
        seen,
    )
    history, stats = [], RunStats()
    events = list(Agent(p).run(history, "¿Qué tiempo hace en Kioto en abril?", ToolContext(), stats))
    assert stats.status == "completed" and events[-1]["text"] == "En abril hay 15 °C de media."
    tool_msg = seen[1]["messages"][-1]
    assert tool_msg["role"] == "tool" and json.loads(tool_msg["content"])["avg_temp_c"] == 15
    assert len(history) == 4


# --- Proveedor protegido -----------------------------------------------------------


class FakeBudget:
    def __init__(self, ok=True):
        self.ok, self.spent, self.cooldowns = ok, 0, []

    def can_call(self):
        return self.ok

    def spend(self, tokens):
        self.spent += tokens

    def cooldown(self, seconds):
        self.cooldowns.append(seconds)


class Scripted:
    name, model = "groq", "fake"

    def __init__(self, items):
        self.items = list(items)

    def complete(self, system, tools, messages):
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def turn(text="hola", inp=100, out=10, cached=40):
    return ModelTurn("end_turn", [Block(type="text", text=text)], [{"type": "text", "text": text}], inp, out, cached)


def test_guarded_spends_uncached_tokens():
    budget = FakeBudget()
    g = GuardedProvider(Scripted([turn()]), DemoProvider(), budget)
    assert g.complete("s", [], [{"role": "user", "content": "x"}]).blocks[0].text == "hola"
    assert budget.spent == 100 - 40 + 10 and g.name == "groq"


def test_guarded_waits_on_short_rate_limit():
    slept = []
    g = GuardedProvider(Scripted([RateLimited(3), turn("tras esperar")]), DemoProvider(), FakeBudget(), sleep=slept.append)
    assert g.complete("s", [], [{"role": "user", "content": "x"}]).blocks[0].text == "tras esperar"
    assert slept == [3.5]


def test_guarded_falls_back_to_demo_on_long_rate_limit():
    budget = FakeBudget()
    g = GuardedProvider(Scripted([RateLimited(600)]), DemoProvider(), budget)
    events = list(Agent(g).run([], "¿Necesito visado para Japón?", ToolContext(), stats := RunStats()))
    assert budget.cooldowns == [600] and g.name == "demo"
    assert any(e["type"] == "notice" and "modo demo" in e["text"] for e in events)
    assert stats.status == "completed" and "Guía de Kioto" in events[-1]["text"]


def test_guarded_uses_demo_when_budget_is_exhausted():
    g = GuardedProvider(Scripted([]), DemoProvider(), FakeBudget(ok=False))
    t = g.complete("s", [], [{"role": "user", "content": "3 días en Lisboa"}])
    assert "presupuesto" in t.notice and g.switched


# --- Límites ---------------------------------------------------------------------


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture(params=["memory", "redis"])
def limits(request):
    clock = Clock()
    store = MemoryCounterStore(clock) if request.param == "memory" else RedisCounterStore(fakeredis.FakeRedis())
    cfg = LimitsConfig(flood_per_minute=3, llm_per_hour=2, llm_per_day=3, daily_token_budget=1000, min_tokens_per_run=300)
    return UsageLimits(store, cfg, clock), clock


def test_flood_limit_per_minute(limits):
    lim, clock = limits
    assert [lim.allow_request("1.1.1.1") for _ in range(4)] == [True, True, True, False]
    assert lim.allow_request("2.2.2.2")  # otra IP no se ve afectada
    clock.t += 60
    assert lim.allow_request("1.1.1.1")  # nuevo minuto


def test_ip_quota_per_hour_and_day(limits):
    lim, clock = limits
    assert lim.take_ip_quota("ip") and lim.take_ip_quota("ip")
    assert not lim.take_ip_quota("ip")  # 2 por hora
    clock.t += 3600
    assert lim.take_ip_quota("ip")
    clock.t += 3600
    assert not lim.take_ip_quota("ip")  # 3 al día
    assert lim.ip_remaining("ip") == {"hour": 2, "day": 0}


def test_token_budget_and_cooldown(limits):
    lim, clock = limits
    assert lim.can_start_run()
    lim.spend(750)
    assert lim.tokens_remaining() == 250 and not lim.can_start_run() and lim.can_call()
    lim.spend(500)
    assert not lim.can_call()
    clock.t += 86_400
    assert lim.can_start_run()  # nuevo día


def test_cooldown_blocks_real_ai(limits):
    lim, clock = limits
    if isinstance(lim.store, RedisCounterStore):
        pytest.skip("el reloj simulado no controla la caducidad de Redis")
    lim.cooldown(30)
    assert not lim.can_start_run()
    clock.t += 31
    assert lim.can_start_run()


def test_client_ip_uses_last_forwarded_entry():
    assert client_ip({"x-forwarded-for": "6.6.6.6, 9.9.9.9"}, "10.0.0.1") == "9.9.9.9"
    assert client_ip({}, "10.0.0.1") == "10.0.0.1"
    # Detrás de Cloudflare (Render), CF-Connecting-IP manda.
    assert client_ip({"cf-connecting-ip": "5.5.5.5", "x-forwarded-for": "5.5.5.5, 172.68.1.1"}, "10.0.0.1") == "5.5.5.5"


# --- API con modelo real simulado ----------------------------------------------------


@pytest.fixture
def real_ai(monkeypatch):
    class FakeReal:
        name, model = "groq", "openai/gpt-oss-120b"

        def complete(self, system, tools, messages):
            return turn("Respuesta del modelo real", inp=200, out=30, cached=0)

    lim = UsageLimits(MemoryCounterStore(), LimitsConfig(flood_per_minute=5, llm_per_hour=1, llm_per_day=5))
    monkeypatch.setattr(main, "real_provider", FakeReal())
    monkeypatch.setattr(main, "limits", lim)
    return lim


def sse(text):
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_ip_over_quota_gets_demo_mode_with_notice(real_ai):
    with TestClient(main.app) as client:
        first = sse(client.post("/api/chat", json={"message": "hola"}).text)
        assert first[0]["mode"] == "groq" and first[-2]["text"] == "Respuesta del modelo real"
        assert real_ai.tokens_remaining() == real_ai.config.daily_token_budget - 230
        second = sse(client.post("/api/chat", json={"message": "¿Necesito visado para Japón?"}).text)
        assert second[0]["mode"] == "demo"
        assert second[1]["type"] == "notice" and "1 por hora" in second[1]["text"]
        usage = client.get("/api/usage").json()
        assert usage["mode"] == "groq" and usage["real_ai"] is False and usage["remaining"]["hour"] == 0


def test_flood_returns_429(real_ai):
    with TestClient(main.app) as client:
        codes = [client.post("/api/chat", json={"message": "hola"}).status_code for _ in range(6)]
        assert codes[:5] == [200] * 5 and codes[5] == 429


def test_usage_in_demo_mode():
    with TestClient(main.app) as client:
        assert client.get("/api/usage").json() == {"mode": "demo", "model": "rumbo-demo", "real_ai": False}


# --- Gemini --------------------------------------------------------------------------


def test_gemini_thought_signatures_are_kept_and_sent_back():
    seen = []
    signature = {"google": {"thought_signature": "firma-123"}}
    call = {**tool_call("get_climate", {"destination_id": "kioto", "month": 4}), "extra_content": signature}
    p = provider_with(
        [httpx.Response(200, json=completion(None, [call], "tool_calls")), httpx.Response(200, json=completion("15 °C"))], seen
    )
    p.model = "gemini-flash-latest"
    events = list(Agent(p).run([], "clima en Kioto en abril", ToolContext(), RunStats()))
    assert events[-1]["text"] == "15 °C"
    sent_call = next(m for m in seen[1]["messages"] if m.get("tool_calls"))["tool_calls"][0]
    assert sent_call["extra_content"] == signature and seen[0]["reasoning_effort"] == "low"


def test_missing_tool_call_id_gets_generated():
    call = {"type": "function", "function": {"name": "get_climate", "arguments": "{}"}}
    turn = OpenAICompatibleProvider._parse(completion(None, [call], "tool_calls"))
    assert turn.blocks[0].id.startswith("call_") and turn.history_content[0]["id"] == turn.blocks[0].id


def test_gemini_key_selects_gemini():
    from app.config import Settings

    s = Settings(_env_file=None, agent_mode="auto", gemini_api_key="g", groq_api_key="q", anthropic_api_key=None)
    assert s.llm_provider == "gemini"
    assert (
        Settings(_env_file=None, agent_mode="auto", groq_api_key="q", anthropic_api_key=None, gemini_api_key=None).llm_provider
        == "groq"
    )
    assert Settings(_env_file=None, gemini_api_key="g", agent_mode="demo", anthropic_api_key=None).llm_provider == "demo"


def test_model_receives_compact_tool_results():
    seen = []
    p = provider_with(
        [
            httpx.Response(
                200, json=completion(None, [tool_call("build_itinerary", {"destination_id": "kioto", "days": 3})], "tool_calls")
            ),
            httpx.Response(200, json=completion("Listo.")),
        ],
        seen,
    )
    events = list(Agent(p).run([], "3 días en Kioto", ToolContext(), RunStats()))
    sent = json.loads(seen[1]["messages"][-1]["content"])
    assert set(sent) == {"destination", "days"} and isinstance(sent["days"][0]["plan"][0], str)
    full = next(e for e in events if e["type"] == "tool_result")["output"]
    assert "activities" in full["days"][0]  # la interfaz sigue recibiendo el detalle completo
