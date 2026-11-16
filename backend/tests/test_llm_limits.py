import json

import fakeredis
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.agent import Agent, RunStats, ToolContext, build_real_providers
from app.limits import LimitsConfig, MemoryCounterStore, RedisCounterStore, UsageLimits, client_ip
from tests.fakes import FakeBudget, HTTPError, ScriptedModel, end_turn, provider

QUESTION = "¿Necesito visado para Japón?"


def run(agent, prompt=QUESTION):
    stats = RunStats()
    events = list(agent.run([], prompt, ToolContext(save_trip=lambda d: {**d, "id": 1}), stats))
    return events, stats


def notices(events):
    return [e["text"] for e in events if e["type"] == "notice"]


# --- Cadena de modelos (middleware) ------------------------------------------------


def test_chain_spends_uncached_tokens():
    budget = FakeBudget()
    agent = Agent([provider([end_turn("hola", inp=100, out=10, cached=40)])], budget=budget)
    events, stats = run(agent, "hola")
    assert events[-1]["text"] == "hola" and agent.current.name == "groq"
    assert budget.spent == 100 - 40 + 10 and stats.input_tokens == 100


def test_chain_falls_back_to_demo_on_rate_limit():
    budget = FakeBudget()
    agent = Agent([provider([HTTPError(429, retry_after="600")])], budget=budget)
    events, stats = run(agent)
    assert budget.cooldowns == [600] and agent.current.name == "demo"
    assert notices(events) == ["Groq ha alcanzado su cuota gratuita: continúo con modo demo."]
    assert stats.status == "completed" and "Guía de Kioto" in events[-1]["text"]


def test_chain_falls_back_to_demo_when_provider_unavailable():
    budget = FakeBudget()
    agent = Agent([provider([HTTPError(503)])], budget=budget)
    events, stats = run(agent)
    assert budget.cooldowns == [30] and agent.current.name == "demo"
    assert "no está disponible" in notices(events)[0] and stats.status == "completed"


def test_chain_uses_demo_when_budget_is_exhausted():
    agent = Agent([provider([])], budget=FakeBudget(ok=False))
    events, stats = run(agent, "3 días en Lisboa")
    assert "presupuesto" in notices(events)[0] and agent.current.name == "demo" and stats.status == "completed"


def test_chain_moves_to_next_provider_when_quota_is_exhausted():
    budget = FakeBudget()
    gemini = provider([HTTPError(402)], name="gemini")
    groq = provider([end_turn("respuesta de Groq")], name="groq")
    agent = Agent([gemini, groq], budget=budget)
    events, _ = run(agent, "hola")
    assert events[-1]["text"] == "respuesta de Groq" and agent.current.name == "groq"
    assert notices(events) == ["Gemini ha alcanzado su cuota gratuita: continúo con Groq."]
    assert budget.paused == ["gemini"] and budget.cooldowns == [3600]


def test_chain_ends_in_demo_when_every_provider_fails():
    budget = FakeBudget()
    chain = [
        provider([HTTPError(429)], name="gemini"),
        provider([HTTPError(503)], name="groq"),
        provider([HTTPError(402)], name="deepseek"),
    ]
    agent = Agent(chain, budget=budget)
    events, stats = run(agent)
    texts = " ".join(notices(events))
    assert "continúo con Groq" in texts and "continúo con DeepSeek" in texts and texts.endswith("modo demo.")
    assert budget.paused == ["gemini", "groq", "deepseek"] and agent.current.name == "demo"
    assert stats.status == "completed"


def test_chain_skips_providers_in_cooldown_without_notice():
    agent = Agent(
        [provider([], name="gemini"), provider([end_turn("de Groq")], name="groq")], budget=FakeBudget(cooling=("gemini",))
    )
    events, _ = run(agent, "hola")
    assert events[-1]["text"] == "de Groq" and not notices(events)


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


def test_provider_cooldown_is_per_provider(limits):
    lim, _ = limits
    lim.cooldown(600, "gemini")
    assert lim.cooling_down("gemini") and not lim.cooling_down("groq") and not lim.cooling_down()
    assert lim.can_start_run()  # el resto de la cadena sigue disponible


# --- API con modelo real simulado ----------------------------------------------------


@pytest.fixture
def real_ai(monkeypatch):
    groq = provider([], name="groq")
    groq.model = "openai/gpt-oss-120b"
    groq.llm = ScriptedModel(items=[end_turn("Respuesta del modelo real", inp=200, out=30) for _ in range(10)])
    lim = UsageLimits(MemoryCounterStore(), LimitsConfig(flood_per_minute=5, llm_per_hour=1, llm_per_day=5))
    monkeypatch.setattr(main, "real_providers", [groq])
    monkeypatch.setattr(main, "limits", lim)
    return lim


def sse(text):
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_ip_over_quota_gets_demo_mode_with_notice(real_ai):
    with TestClient(main.app) as client:
        first = sse(client.post("/api/chat", json={"message": "hola"}).text)
        assert first[0]["mode"] == "groq" and first[-2]["text"] == "Respuesta del modelo real"
        assert real_ai.tokens_remaining() == real_ai.config.daily_token_budget - 230
        second = sse(client.post("/api/chat", json={"message": QUESTION}).text)
        assert second[0]["mode"] == "demo"
        assert second[1]["type"] == "notice" and "1 por hora" in second[1]["text"]
        usage = client.get("/api/usage").json()
        assert usage["mode"] == "groq" and usage["real_ai"] is False and usage["remaining"]["hour"] == 0


def test_user_can_force_demo_mode_without_spending_quota(real_ai):
    with TestClient(main.app) as client:
        events = sse(client.post("/api/chat", json={"message": "hola", "mode": "demo"}).text)
        assert events[0]["mode"] == "demo" and not any(e["type"] == "notice" for e in events)
        assert real_ai.tokens_remaining() == real_ai.config.daily_token_budget
        assert client.get("/api/usage").json()["remaining"]["hour"] == 1  # el cupo sigue intacto
        assert sse(client.post("/api/chat", json={"message": "hola"}).text)[0]["mode"] == "groq"
        assert client.post("/api/chat", json={"message": "hola", "mode": "otro"}).status_code == 422


def test_flood_returns_429(real_ai):
    with TestClient(main.app) as client:
        codes = [client.post("/api/chat", json={"message": "hola"}).status_code for _ in range(6)]
        assert codes[:5] == [200] * 5 and codes[5] == 429


def test_usage_in_demo_mode():
    with TestClient(main.app) as client:
        assert client.get("/api/usage").json() == {"mode": "demo", "model": "rumbo-demo", "real_ai": False}


def test_api_skips_provider_in_cooldown(monkeypatch):
    gemini = provider([end_turn("Respuesta de gemini")], name="gemini")
    groq = provider([end_turn("Respuesta de groq")], name="groq")
    lim = UsageLimits(MemoryCounterStore(), LimitsConfig())
    lim.cooldown(3600, "gemini")
    monkeypatch.setattr(main, "real_providers", [gemini, groq])
    monkeypatch.setattr(main, "limits", lim)
    with TestClient(main.app) as client:
        usage = client.get("/api/usage").json()
        assert usage["mode"] == "groq" and usage["chain"] == ["gemini", "groq"] and usage["real_ai"] is True
        events = sse(client.post("/api/chat", json={"message": "hola"}).text)
        assert events[0]["mode"] == "groq" and events[-2]["text"] == "Respuesta de groq"
        lim.cooldown(3600, "groq")
        events = sse(client.post("/api/chat", json={"message": "hola"}).text)
        assert events[0]["mode"] == "demo" and "agotado su cuota" in events[1]["text"]


# --- Configuración -----------------------------------------------------------------


def test_providers_are_langchain_chat_models():
    from app.config import Settings

    s = Settings(
        _env_file=None,
        agent_mode="auto",
        anthropic_api_key="a",
        gemini_api_key="g",
        groq_api_key="q",
        extra_llm_api_key="hf",
    )
    providers = build_real_providers(s)
    assert [p.name for p in providers] == ["claude", "gemini", "groq", "deepseek"]
    assert [type(p.llm).__name__ for p in providers] == ["ChatAnthropic", "ChatGoogleGenerativeAI", "ChatOpenAI", "ChatOpenAI"]
    assert providers[3].label == "DeepSeek" and providers[3].model == "deepseek/deepseek-v4-flash:free"


def test_gemini_key_selects_gemini():
    from app.config import Settings

    s = Settings(_env_file=None, agent_mode="auto", gemini_api_key="g", groq_api_key="q", anthropic_api_key=None)
    assert s.llm_provider == "gemini"
    assert (
        Settings(_env_file=None, agent_mode="auto", groq_api_key="q", anthropic_api_key=None, gemini_api_key=None).llm_provider
        == "groq"
    )
    assert Settings(_env_file=None, gemini_api_key="g", agent_mode="demo", anthropic_api_key=None).llm_provider == "demo"


def test_settings_build_the_chain_in_priority_order():
    from app.config import Settings

    s = Settings(
        _env_file=None, agent_mode="auto", anthropic_api_key=None, gemini_api_key="g", groq_api_key="q", extra_llm_api_key="hf"
    )
    assert s.llm_chain == ["gemini", "groq", "extra"] and s.llm_provider == "gemini"
    only_extra = Settings(
        _env_file=None, agent_mode="auto", anthropic_api_key=None, gemini_api_key=None, groq_api_key=None, extra_llm_api_key="hf"
    )
    assert only_extra.llm_chain == ["extra"] and only_extra.extra_llm_base_url == "https://openrouter.ai/api/v1"
    assert Settings(_env_file=None, agent_mode="demo", gemini_api_key="g", anthropic_api_key=None).llm_chain == []
