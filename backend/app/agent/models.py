"""Modelos de IA que puede usar el agente.

Cada proveedor es un modelo de chat de LangChain (`ChatAnthropic`, `ChatGoogleGenerativeAI`,
`ChatOpenAI`...). LangChain traduce el formato de cada API, así que el agente trabaja igual
con cualquiera de ellos. El modo demo es un modelo más (`DemoChatModel`), que no usa IA.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from ..config import Settings
from .demo import DemoChatModel

LABELS = {
    "claude": "Claude",
    "gemini": "Gemini",
    "groq": "Groq",
    "deepseek": "DeepSeek",
    "huggingface": "Hugging Face",
    "openrouter": "OpenRouter",
}


@dataclass
class Provider:
    name: str  # "claude", "gemini", "groq", "demo"...: identifica sus cuotas y pausas
    model: str  # id del modelo, para mostrarlo en la interfaz
    llm: BaseChatModel  # el modelo de chat de LangChain

    @property
    def label(self) -> str:
        """Nombre legible para los avisos: "huggingface" → "Hugging Face"."""
        return LABELS.get(self.name, self.name[:1].upper() + self.name[1:])


def demo_provider(delay_s: float = 0.0) -> Provider:
    return Provider("demo", "rumbo-demo", DemoChatModel(delay_s=delay_s))


def build_real_providers(settings: Settings) -> list[Provider]:
    """Modelos reales con clave configurada, en orden de prioridad. Lista vacía: modo demo."""
    providers: list[Provider] = []
    for name in settings.llm_chain:
        if name == "claude":
            from langchain_anthropic import ChatAnthropic

            llm = ChatAnthropic(model=settings.agent_model, api_key=settings.anthropic_api_key, max_tokens=8000)
            providers.append(Provider("claude", settings.agent_model, llm))
        elif name == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model=settings.gemini_model,
                google_api_key=settings.gemini_api_key,
                max_output_tokens=settings.llm_max_output_tokens,
                temperature=0.3,
            )
            providers.append(Provider("gemini", settings.gemini_model, llm))
        elif name == "groq":
            providers.append(
                _openai_compatible("groq", settings.groq_model, settings.groq_base_url, settings.groq_api_key, settings)
            )
        elif name == "extra":
            providers.append(
                _openai_compatible(
                    settings.extra_llm_name,
                    settings.extra_llm_model,
                    settings.extra_llm_base_url,
                    settings.extra_llm_api_key,
                    settings,
                )
            )
    return providers


def _openai_compatible(name: str, model: str, base_url: str, api_key: str | None, settings: Settings) -> Provider:
    """Cualquier API compatible con OpenAI (Groq, Hugging Face, OpenRouter, DeepSeek...)."""
    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        max_tokens=settings.llm_max_output_tokens,
        temperature=0.3,
        # Menos tokens de razonamiento en los modelos que lo admiten: cuidan la cuota gratuita.
        reasoning_effort="low" if model.startswith("openai/gpt-oss") else None,
        timeout=45,
    )
    return Provider(name, model, llm)
