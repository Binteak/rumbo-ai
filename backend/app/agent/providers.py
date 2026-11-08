"""Proveedores de modelo.

El loop del agente no conoce ningún SDK: habla con un `ModelProvider` que devuelve
un `ModelTurn` normalizado. Así se puede cambiar de modelo, o usar el modo demo
sin API key, sin tocar el loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Block:
    type: str  # "text" | "tool_use"
    text: str = ""
    id: str = ""
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelTurn:
    stop_reason: str  # "tool_use" | "end_turn" | "max_tokens" | "refusal" | ...
    blocks: list[Block]
    history_content: Any  # contenido exacto que hay que guardar en el historial
    input_tokens: int = 0
    output_tokens: int = 0


class ModelProvider(Protocol):
    name: str
    model: str

    def complete(self, system: str, tools: list[dict], messages: list[dict]) -> ModelTurn: ...


class AnthropicProvider:
    """Claude vía la API de Anthropic."""

    name = "claude"

    def __init__(self, api_key: str, model: str, effort: str = "medium", max_tokens: int = 8000) -> None:
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens

    def complete(self, system: str, tools: list[dict], messages: list[dict]) -> ModelTurn:
        response = self.client.beta.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            tools=tools,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            # Si un clasificador de seguridad rechaza la petición, la API reintenta
            # con un modelo de respaldo.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        blocks = []
        for b in response.content:
            if b.type == "text" and b.text:
                blocks.append(Block(type="text", text=b.text))
            elif b.type == "tool_use":
                blocks.append(Block(type="tool_use", id=b.id, name=b.name, input=dict(b.input)))
        usage = response.usage
        return ModelTurn(
            stop_reason=response.stop_reason or "end_turn",
            blocks=blocks,
            # Se guardan todos los bloques (incluidos los de thinking con su firma): la API los
            # necesita sin modificar. Como dicts JSON para poder persistirlos en Redis.
            history_content=[b.model_dump(mode="json", exclude_none=True) for b in response.content],
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )
