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
    # "auto": Claude si hay ANTHROPIC_API_KEY; si no, Gemini (GEMINI_API_KEY); si no, Groq (GROQ_API_KEY);
    # y si no, el modo demo.
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
    def llm_provider(self) -> str:
        """Proveedor real configurado: "claude", "gemini", "groq" o "demo" si no hay ninguno."""
        if self.agent_mode == "demo":
            return "demo"
        if self.anthropic_api_key:
            return "claude"
        if self.gemini_api_key:
            return "gemini"
        if self.groq_api_key:
            return "groq"
        return "demo"

    @property
    def use_demo(self) -> bool:
        return self.llm_provider == "demo"

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
