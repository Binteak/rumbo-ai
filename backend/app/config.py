"""Configuración de la aplicación (variables de entorno o fichero .env)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str | None = None
    agent_model: str = "claude-sonnet-5-5"
    agent_effort: str = "medium"
    agent_max_iterations: int = 12
    # "auto": cadena con los proveedores que tengan clave, en este orden:
    #   Claude (ANTHROPIC_API_KEY) → Gemini (GEMINI_API_KEY) → Groq (GROQ_API_KEY) → extra (EXTRA_LLM_API_KEY).
    # Si uno agota su cuota o no responde, el turno sigue con el siguiente; al final de la cadena, el modo demo.
    # "demo" fuerza el modo demo.
    agent_mode: str = "auto"
    demo_delay_ms: int = 700

    # Modelos gratuitos con APIs compatibles con OpenAI (sin tarjeta): Gemini (Google AI Studio) y Groq.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-latest"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    groq_api_key: str | None = None
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # Proveedor extra: cualquier API compatible con OpenAI (Hugging Face, OpenRouter, DeepSeek...).
    # Por defecto, el router de Hugging Face; para otro, cambia la URL, el modelo y el nombre.
    extra_llm_api_key: str | None = None
    extra_llm_name: str = "huggingface"
    extra_llm_model: str = "openai/gpt-oss-120b"
    extra_llm_base_url: str = "https://router.huggingface.co/v1"
    llm_max_output_tokens: int = 2048

    # Protección y presupuesto (ver app/limits.py). El presupuesto diario por defecto deja margen
    # bajo los 200.000 tokens/día del plan gratuito de Groq.
    rate_limit_flood_per_minute: int = 20
    rate_limit_llm_per_hour: int = 5
    rate_limit_llm_per_day: int = 15
    llm_daily_token_budget: int = 180_000
    llm_min_tokens_per_run: int = 12_000

    # RAG: con VOYAGE_API_KEY usa embeddings de Voyage AI; sin ella, un embedder local gratuito.
    voyage_api_key: str | None = None
    embedding_model: str = "voyage-4-lite"
    rag_top_k: int = 4

    database_url: str = "sqlite:///./rumbo.db"
    # Con REDIS_URL el historial de sesiones se guarda en Redis (necesario con varias réplicas).
    redis_url: str | None = None
    cors_origins: str = "http://localhost:4200"

    @property
    def llm_chain(self) -> list[str]:
        """Proveedores reales con clave, en orden de prioridad ("claude", "gemini", "groq", "extra")."""
        if self.agent_mode == "demo":
            return []
        keys = {
            "claude": self.anthropic_api_key,
            "gemini": self.gemini_api_key,
            "groq": self.groq_api_key,
            "extra": self.extra_llm_api_key,
        }
        return [name for name, key in keys.items() if key]

    @property
    def llm_provider(self) -> str:
        """Primer proveedor de la cadena, o "demo" si no hay ninguno."""
        chain = self.llm_chain
        return chain[0] if chain else "demo"

    @property
    def use_demo(self) -> bool:
        return self.llm_provider == "demo"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
