"""Persistencia con SQLAlchemy 2.0 (SQLite por defecto, PostgreSQL cambiando DATABASE_URL)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, create_engine, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


class Trip(Base):
    """Viaje planificado y guardado por el agente."""

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    title: Mapped[str] = mapped_column(String(160))
    destination_id: Mapped[str] = mapped_column(String(40))
    destination_name: Mapped[str] = mapped_column(String(80))
    flag: Mapped[str] = mapped_column(String(8), default="")
    month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    days: Mapped[int] = mapped_column(Integer)
    travelers: Mapped[int] = mapped_column(Integer)
    style: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text, default="")
    climate: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    budget: Mapped[dict] = mapped_column(JSON)
    itinerary: Mapped[list] = mapped_column(JSON)


class AgentRun(Base):
    """Traza resumida de cada ejecución del agente (observabilidad)."""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    prompt: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(String(10))
    model: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(20))
    iterations: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_errors: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    trip_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


_settings = get_settings()
engine = create_engine(
    _settings.database_url,
    connect_args={"check_same_thread": False} if _settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    with engine.begin() as conn:
        if conn.dialect.name == "postgresql":
            # Con varias réplicas arrancando a la vez, solo una crea las tablas: las demás esperan
            # a este bloqueo y después ven que ya existen.
            conn.execute(text("SELECT pg_advisory_xact_lock(727274)"))
        Base.metadata.create_all(conn)


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db
