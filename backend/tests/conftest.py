import os

# Antes de importar la app: BD temporal, modo demo y sin pausas.
os.environ["DATABASE_URL"] = "sqlite:///./test_rumbo.db"
os.environ["AGENT_MODE"] = "demo"
os.environ["DEMO_DELAY_MS"] = "0"

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _cleanup_db():
    yield
    if os.path.exists("test_rumbo.db"):
        os.remove("test_rumbo.db")
