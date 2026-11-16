"""Modelos falsos para los tests: devuelven respuestas predefinidas sin llamar a ninguna API."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from app.agent import Provider


class ScriptedModel(BaseChatModel):
    """Devuelve, en orden, los mensajes (o lanza las excepciones) de `items` y guarda lo que recibe."""

    items: list[Any] = Field(default_factory=list)
    calls: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedModel:
        return self

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None, **kwargs: Any) -> ChatResult:
        self.calls.append(list(messages))
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return ChatResult(generations=[ChatGeneration(message=item)])


def usage(inp: int = 10, out: int = 5, cached: int = 0) -> dict:
    return {
        "input_tokens": inp,
        "output_tokens": out,
        "total_tokens": inp + out,
        "input_token_details": {"cache_read": cached},
    }


def tool_turn(name: str, args: dict, tid: str = "t1") -> AIMessage:
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": tid, "type": "tool_call"}], usage_metadata=usage()
    )


def end_turn(text: str, inp: int = 10, out: int = 5, cached: int = 0) -> AIMessage:
    return AIMessage(content=text, usage_metadata=usage(inp, out, cached))


def provider(items: list[Any], name: str = "groq") -> Provider:
    return Provider(name, f"{name}-model", ScriptedModel(items=items))


class HTTPError(Exception):
    """Error como los que lanzan los SDK de los proveedores (con código HTTP y cabeceras)."""

    def __init__(self, status_code: int, retry_after: str | None = None) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code
        self.response = type(
            "Response", (), {"status_code": status_code, "headers": {"retry-after": retry_after} if retry_after else {}}
        )()


class FakeBudget:
    def __init__(self, ok: bool = True, cooling: tuple[str, ...] = ()) -> None:
        self.ok, self.spent, self.cooldowns, self.paused = ok, 0, [], []
        self.cooling = set(cooling)

    def can_call(self) -> bool:
        return self.ok

    def spend(self, tokens: int) -> None:
        self.spent += tokens

    def cooldown(self, seconds: float, provider: str | None = None) -> None:
        self.cooldowns.append(seconds)
        self.paused.append(provider)

    def cooling_down(self, provider: str | None = None) -> bool:
        return provider in self.cooling
