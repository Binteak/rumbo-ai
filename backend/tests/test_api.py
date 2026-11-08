import json

from fastapi.testclient import TestClient

from app.main import app


def parse_sse(text):
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_health_reports_demo_mode():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["mode"] == "demo"


def test_chat_streams_events_and_persists_trip_and_run():
    with TestClient(app) as client:
        r = client.post("/api/chat", json={"message": "4 días en Lisboa en junio, gastronomía y fado"})
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
        events = parse_sse(r.text)
        assert events[0]["type"] == "run_started"
        assert events[-1]["type"] == "done" and events[-1]["stats"]["status"] == "completed"
        trip = next(e["trip"] for e in events if e["type"] == "trip")
        assert trip["destination_id"] == "lisboa" and len(trip["itinerary"]) == 4

        assert client.get(f"/api/trips/{trip['id']}").json()["title"] == trip["title"]
        assert any(t["id"] == trip["id"] for t in client.get("/api/trips").json())
        stats = client.get("/api/stats").json()
        assert stats["runs"] >= 1 and stats["trips"] >= 1

        # La sesión recuerda el contexto: el segundo mensaje solo cambia los días.
        session = events[0]["session_id"]
        events2 = parse_sse(client.post("/api/chat", json={"message": "mejor 2 días", "session_id": session}).text)
        trip2 = next(e["trip"] for e in events2 if e["type"] == "trip")
        assert trip2["destination_id"] == "lisboa" and trip2["days"] == 2

        assert client.delete(f"/api/trips/{trip['id']}").status_code == 204
        assert client.get(f"/api/trips/{trip['id']}").status_code == 404


def test_ready_checks_dependencies():
    with TestClient(app) as client:
        r = client.get("/api/ready")
        assert r.status_code == 200
        assert r.json()["checks"] == {"database": "ok", "sessions": "ok"}


def test_chat_validates_input():
    with TestClient(app) as client:
        assert client.post("/api/chat", json={"message": ""}).status_code == 422
