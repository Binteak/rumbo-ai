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
_last_error: dict[str, str | None] = {"message": None}


class _RememberLangSmithErrors(logging.Handler):
    """Guarda el último aviso de la librería de LangSmith (p. ej. si rechaza las trazas al enviarlas)."""

    def emit(self, record: logging.LogRecord) -> None:
        # La propia librería ya enmascara la clave ("lsv2_**ab"); se recorta por si acaso.
        _last_error["message"] = record.getMessage().split("\n")[0][:300]


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
    info["test_trace"] = _check.get("test_trace")
    info["last_error"] = _last_error["message"]
    return info


def check_in_background() -> None:
    """Comprueba una vez, sin retrasar el arranque, que LangSmith acepta la clave."""
    info = destination()
    if not info["enabled"]:
        log.info("LangSmith: trazas desactivadas")
        return
    handler = _RememberLangSmithErrors(level=logging.WARNING)
    logging.getLogger("langsmith").addHandler(handler)
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
            return
        _check["test_trace"] = _send_test_trace(info.get("project"))
        log.info("LangSmith: traza de prueba → %s", _check["test_trace"])

    threading.Thread(target=run, daemon=True).start()


def _send_test_trace(project: str | None) -> str:
    """Envía una traza mínima sin agrupar en lotes, para ver si LangSmith la acepta y dónde queda."""
    import time
    import uuid
    from datetime import UTC, datetime

    from langsmith import Client

    client = Client(auto_batch_tracing=False)
    run_id = uuid.uuid4()
    now = datetime.now(UTC)
    try:
        client.create_run(
            "Rumbo · prueba de conexión",
            {"mensaje": "Traza de prueba enviada al arrancar el backend"},
            "chain",
            id=run_id,
            project_name=project,
            start_time=now,
            end_time=now,
            outputs={"ok": True},
        )
    except Exception as e:  # noqa: BLE001 - es justo lo que se quiere saber
        return f"rechazada: {str(e).splitlines()[0][:200]}"
    for _ in range(10):  # la ingesta es asíncrona: se espera a que aparezca
        time.sleep(2)
        try:
            run = client.read_run(run_id)
            where = client.read_project(project_id=str(run.session_id)).name
            return f"aceptada y guardada en el proyecto '{where}'"
        except Exception:  # noqa: BLE001, S112 - aún no está disponible
            continue
    return "aceptada por la API, pero no aparece al leerla (¿otro espacio de trabajo?)"
