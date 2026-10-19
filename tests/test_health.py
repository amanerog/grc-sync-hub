from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from sinc_amn.api.routes import health
from sinc_amn.main import app


def test_health_returns_ok():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class _FakeMaisaClient:
    error: Exception | None = None

    async def check_connection(self):
        if _FakeMaisaClient.error:
            raise _FakeMaisaClient.error
        return {"database": "gpp_maisa_metrics", "collections": ["worker"]}


def test_maisa_db_health_ok(monkeypatch):
    _FakeMaisaClient.error = None
    monkeypatch.setattr(health, "MaisaClient", _FakeMaisaClient)

    response = TestClient(app).get("/health/maisa-db")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "database": "gpp_maisa_metrics",
        "collections": ["worker"],
    }


def test_maisa_db_health_returns_503_on_mongo_error(monkeypatch):
    _FakeMaisaClient.error = ServerSelectionTimeoutError("timed out")
    monkeypatch.setattr(health, "MaisaClient", _FakeMaisaClient)

    response = TestClient(app).get("/health/maisa-db")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "error": "ServerSelectionTimeoutError",
        "detail": "timed out",
    }
