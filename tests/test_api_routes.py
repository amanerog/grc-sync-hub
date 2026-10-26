from datetime import date

import httpx
from fastapi.testclient import TestClient

from sinc_amn.api.routes import checkpoints, noxus_labels, use_cases, workers
from sinc_amn.main import app


class _FakeService:
    calls: list = []
    summary = {"total": 0, "succeeded": 0, "failed": 0}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _FakeService.calls.append(("init", kwargs))

    async def run(self, **kwargs):
        _FakeService.calls.append(("run", kwargs or None))
        return _FakeService.summary


def test_sync_noxus_labels_endpoint(monkeypatch):
    _FakeService.calls = []
    _FakeService.summary = {"total": 2, "succeeded": 2, "failed": 0}
    monkeypatch.setattr(noxus_labels, "NoxusLabelSyncService", _FakeService)
    monkeypatch.setattr(noxus_labels, "get_pool", lambda: object())

    response = TestClient(app).post("/flows/noxus-labels/sync")

    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "total": 2,
        "succeeded": 2,
        "failed": 0,
    }
    assert ("run", None) in _FakeService.calls


def test_sync_noxus_labels_endpoint_returns_207_on_partial_failure(monkeypatch):
    _FakeService.calls = []
    _FakeService.summary = {"total": 2, "succeeded": 1, "failed": 1}
    monkeypatch.setattr(noxus_labels, "NoxusLabelSyncService", _FakeService)
    monkeypatch.setattr(noxus_labels, "get_pool", lambda: object())

    response = TestClient(app).post("/flows/noxus-labels/sync")

    assert response.status_code == 207
    assert response.json() == {
        "status": "accepted",
        "total": 2,
        "succeeded": 1,
        "failed": 1,
    }


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
    monkeypatch.setattr(workers, "get_pool", lambda: object())

    response = TestClient(app).post("/flows/workers/sync")

    assert response.status_code == 202
    assert response.json() == {
        "status": "accepted",
        "total": 1,
        "succeeded": 1,
        "failed": 0,
    }
    assert ("run", {"day": None}) in _FakeService.calls


def test_sync_workers_endpoint_passes_day_query_param(monkeypatch):
    _FakeService.calls = []
    _FakeService.summary = {"total": 0, "succeeded": 0, "failed": 0}
    monkeypatch.setattr(workers, "WorkerSyncService", _FakeService)
    monkeypatch.setattr(workers, "get_pool", lambda: object())

    response = TestClient(app).post("/flows/workers/sync?day=2026-10-14")

    assert response.status_code == 202
    assert ("run", {"day": date(2026, 10, 14)}) in _FakeService.calls


class _FakeCheckpointService:
    agent = None
    use_case = None
    error: Exception | None = None

    async def get_agent(self, worker_id):
        if self.error:
            raise self.error
        return self.agent

    async def get_use_case(self, use_case_id):
        if self.error:
            raise self.error
        return self.use_case


def _checkpoint_client(monkeypatch, **attrs):
    fake = _FakeCheckpointService()
    for name, value in attrs.items():
        setattr(fake, name, value)
    monkeypatch.setattr(checkpoints, "_service", lambda: fake)
    return TestClient(app)


def test_agent_checkpoint_returns_service_result(monkeypatch):
    agent = {"worker_id": "v-1", "agent_id": "54161", "use_case_id": "51571"}
    client = _checkpoint_client(monkeypatch, agent=agent)

    response = client.get("/checkpoints/agents/v-1")

    assert response.status_code == 200
    assert response.json() == agent


def test_agent_checkpoint_404_for_unknown_version(monkeypatch):
    client = _checkpoint_client(monkeypatch)

    assert client.get("/checkpoints/agents/v-404").status_code == 404


def test_agent_checkpoint_502_when_openpages_fails(monkeypatch):
    client = _checkpoint_client(monkeypatch, error=httpx.ConnectError("boom"))

    response = client.get("/checkpoints/agents/v-1")

    assert response.status_code == 502
    assert response.json() == {"detail": "ConnectError"}


def test_use_case_checkpoint_returns_service_result(monkeypatch):
    use_case = {"use_case_id": "1", "name": "x", "status": "s", "owner": None}
    client = _checkpoint_client(monkeypatch, use_case=use_case)

    response = client.get("/checkpoints/use-cases/1")

    assert response.status_code == 200
    assert response.json() == use_case


def test_use_case_checkpoint_404_when_missing(monkeypatch):
    client = _checkpoint_client(monkeypatch)

    assert client.get("/checkpoints/use-cases/1").status_code == 404
