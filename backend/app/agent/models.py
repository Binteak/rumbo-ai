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

# Nombre legible de cada proveedor para la interfaz.
LABELS = {
    "claude": "Claude",
    "gemini": "Gemini",
    "groq": "Groq",
    "deepseek": "DeepSeek",
    "huggingface": "Hugging Face",
    "openrouter": "OpenRouter",
}


# Un proveedor de la cadena: su modelo de chat de LangChain y los datos para cuotas y avisos.
@dataclass
class Provider:
    name: str  # "claude", "gemini", "groq", "demo"...: identifica sus cuotas y pausas
    model: str  # id del modelo, para mostrarlo en la interfaz
    llm: BaseChatModel  # el modelo de chat de LangChain
    # Llamadas al día que permite su plan gratuito (None: sin límite conocido). Es orientativo:
    # Rumbo cuenta sus propias llamadas, y el proveedor puede contar distinto (p. ej. por proyecto).
    daily_requests: int | None = None

    @property
    def label(self) -> str:
        """Nombre legible para los avisos: "huggingface" → "Hugging Face"."""
        return LABELS.get(self.name, self.name[:1].upper() + self.name[1:])


# Modo demo: un modelo de chat falso que responde sin IA (sin coste).
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
            providers.append(Provider("gemini", settings.gemini_model, llm, settings.gemini_daily_requests))
        elif name == "groq":
            groq = _openai_compatible("groq", settings.groq_model, settings.groq_base_url, settings.groq_api_key, settings)
            groq.daily_requests = settings.groq_daily_requests
            providers.append(groq)
        elif name == "extra":
            extra = _openai_compatible(
                settings.extra_llm_name,
                settings.extra_llm_model,
                settings.extra_llm_base_url,
                settings.extra_llm_api_key,
                settings,
            )
            extra.daily_requests = settings.extra_llm_daily_requests
            providers.append(extra)
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
