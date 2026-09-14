from fastapi.testclient import TestClient

from sinc_amn.api.routes import maisa_labels, use_cases, workers
from sinc_amn.main import app


class _FakeService:
    calls: list = []
    summary = {"total": 0, "succeeded": 0, "failed": 0}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _FakeService.calls.append(("init", kwargs))

    async def run(self):
        _FakeService.calls.append(("run", None))
        return _FakeService.summary


def test_sync_maisa_labels_endpoint(monkeypatch):
    _FakeService.calls = []
    _FakeService.summary = {"total": 2, "succeeded": 2, "failed": 0}
    monkeypatch.setattr(maisa_labels, "MaisaLabelSyncService", _FakeService)
    monkeypatch.setattr(maisa_labels, "get_pool", lambda: object())

    response = TestClient(app).post("/flows/maisa-labels/sync")

    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "total": 2,
        "succeeded": 2,
        "failed": 0,
    }
    assert ("run", None) in _FakeService.calls


def test_sync_use_cases_endpoint(monkeypatch):
    _FakeService.calls = []
    _FakeService.summary = {"total": 2, "succeeded": 2, "failed": 0}
    monkeypatch.setattr(use_cases, "UseCaseSyncService", _FakeService)
    monkeypatch.setattr(use_cases, "get_pool", lambda: object())

    response = TestClient(app).post("/flows/use-cases/sync")

    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "total": 2,
        "succeeded": 2,
        "failed": 0,
    }
    assert ("run", None) in _FakeService.calls


def test_sync_use_cases_endpoint_returns_207_on_partial_failure(monkeypatch):
    _FakeService.calls = []
    _FakeService.summary = {"total": 2, "succeeded": 1, "failed": 1}
    monkeypatch.setattr(use_cases, "UseCaseSyncService", _FakeService)
    monkeypatch.setattr(use_cases, "get_pool", lambda: object())

    response = TestClient(app).post("/flows/use-cases/sync")

    assert response.status_code == 207
    assert response.json() == {
        "status": "accepted",
        "total": 2,
        "succeeded": 1,
        "failed": 1,
    }


def test_sync_workers_endpoint(monkeypatch):
    _FakeService.calls = []
    _FakeService.summary = {"total": 1, "succeeded": 1, "failed": 0}
    monkeypatch.setattr(workers, "WorkerSyncService", _FakeService)

    response = TestClient(app).post("/flows/workers/sync")

    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "total": 1,
        "succeeded": 1,
        "failed": 0,
    }
    assert ("run", None) in _FakeService.calls
