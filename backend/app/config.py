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
    # "auto": usa Claude si hay API key y el modo demo si no. "demo" fuerza el modo demo.
    agent_mode: str = "auto"
    demo_delay_ms: int = 700

    # RAG: con VOYAGE_API_KEY usa embeddings de Voyage AI; sin ella, un embedder local gratuito.
    voyage_api_key: str | None = None
    embedding_model: str = "voyage-4-lite"
    rag_top_k: int = 4

    database_url: str = "sqlite:///./rumbo.db"
    # Con REDIS_URL el historial de sesiones se guarda en Redis (necesario con varias réplicas).
    redis_url: str | None = None
    cors_origins: str = "http://localhost:4200"

    @property
    def use_demo(self) -> bool:
        return self.agent_mode == "demo" or not self.anthropic_api_key

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
