"""Estado de las trazas en LangSmith, para comprobar la configuración sin entrar en los logs.

LangChain envía las trazas por su cuenta cuando ve LANGSMITH_TRACING=true. Aquí solo se
describe a dónde van (agente y entorno, o proyecto) y se comprueba una vez que la clave
funciona, para mostrarlo en /api/health. Nunca se expone la clave.
"""

from __future__ import annotations

import logging
import os
import threading
from importlib.metadata import PackageNotFoundError, version

log = logging.getLogger("uvicorn.error")

_check: dict[str, str] = {"status": "pendiente"}


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def destination() -> dict:
    """A dónde envía LangChain las trazas según las variables de entorno."""
    enabled = _env("LANGSMITH_TRACING").lower() in ("true", "1", "yes")
    try:
        sdk = version("langsmith")
    except PackageNotFoundError:
        sdk = None
    info: dict = {"enabled": enabled, "sdk": sdk}
    if not enabled:
        return info
    agent, environment, project = _env("LANGSMITH_AGENT_ID"), _env("LANGSMITH_AGENT_ENVIRONMENT"), _env("LANGSMITH_PROJECT")
    problems = []
    if not _env("LANGSMITH_API_KEY"):
        problems.append("falta LANGSMITH_API_KEY")
    if (agent or environment) and project:
        problems.append("LANGSMITH_PROJECT y LANGSMITH_AGENT_* a la vez: LangSmith no traza; quita una de las dos")
    elif bool(agent) != bool(environment):
        problems.append("faltan LANGSMITH_AGENT_ID o LANGSMITH_AGENT_ENVIRONMENT")
    if agent and environment:
        info["agent"] = f"{agent}/{environment}"
    elif project:
        info["project"] = project
    else:
        info["project"] = "default"
    info["problems"] = problems
    info["check"] = _check["status"]
    return info


def check_in_background() -> None:
    """Comprueba una vez, sin retrasar el arranque, que LangSmith acepta la clave."""
    info = destination()
    if not info["enabled"]:
        log.info("LangSmith: trazas desactivadas")
        return
    where = info.get("agent") or info.get("project")
    log.info("LangSmith: trazas activadas → %s (langsmith %s)", where, info["sdk"])
    for problem in info["problems"]:
        log.warning("LangSmith: %s", problem)

    def run() -> None:
        try:
            from langsmith import Client

            next(iter(Client().list_projects(limit=1)), None)
            _check["status"] = "ok"
            log.info("LangSmith: clave válida")
        except Exception as e:  # noqa: BLE001 - solo se informa
            _check["status"] = f"error: {type(e).__name__}"
            log.warning("LangSmith no acepta la conexión o la clave: %s", type(e).__name__)

    threading.Thread(target=run, daemon=True).start()
