from datetime import date

from sinc_amn.models.worker import Worker
from sinc_amn.repositories.worker_sync_failure_repository import (
    WorkerSyncFailureRepository,
)

from ._asyncpg_fakes import FakeConnection, FakePool


def _worker(**overrides) -> Worker:
    data = dict(
        worker_id="W-1",
        workspace_id="WS-1",
        tenant="maisa",
        use_case_id="UC-1",
        updated_at=date(2026, 7, 27),
        agent_name="Agente de prueba",
        agent_description="Descripcion de prueba",
        agent_owner="agent-owner@example.com",
        provider_version_id="v1.0",
    )
    data.update(overrides)
    return Worker(**data)


async def test_record_failure_executes_upsert_with_worker_snapshot():
    conn = FakeConnection()
    repo = WorkerSyncFailureRepository(FakePool(conn))
    worker = _worker()

    await repo.record_failure(worker, error="boom")

    assert len(conn.execute_calls) == 1
    query, args = conn.execute_calls[0]
    assert "INSERT INTO worker_sync_failures" in query
    assert "ON CONFLICT" in query
    assert args[0] == "W-1"
    assert args[1] == "WS-1"
    assert args[2] == "maisa"
    assert args[3] == "UC-1"
    assert args[4] == date(2026, 7, 27)
    assert args[5] == "Agente de prueba"
    assert args[6] == "Descripcion de prueba"
    assert args[7] == "agent-owner@example.com"
    assert args[8] == "v1.0"
    assert args[9] == "boom"


async def test_mark_resolved_executes_update_with_worker_id():
    conn = FakeConnection()
    repo = WorkerSyncFailureRepository(FakePool(conn))

    await repo.mark_resolved("W-1")

    assert len(conn.execute_calls) == 1
    query, args = conn.execute_calls[0]
    assert "UPDATE worker_sync_failures" in query
    assert args[0] == "W-1"


async def test_get_pending_reconstructs_workers_from_snapshot():
    conn = FakeConnection(
        fetch_result=[
            {
                "worker_id": "W-1",
                "workspace_id": "WS-1",
                "tenant": "maisa",
                "use_case_id": "UC-1",
                "worker_updated_at": date(2026, 7, 27),
                "agent_name": "Agente de prueba",
                "agent_description": "Descripcion de prueba",
                "agent_owner": "agent-owner@example.com",
                "provider_version_id": "v1.0",
            },
            {
                "worker_id": "W-2",
                "workspace_id": "WS-2",
                "tenant": "noxus",
                "use_case_id": None,
                "worker_updated_at": date(2026, 7, 26),
                "agent_name": None,
                "agent_description": None,
                "agent_owner": None,
                "provider_version_id": None,
            },
        ]
    )
    repo = WorkerSyncFailureRepository(FakePool(conn))

    pending = await repo.get_pending()

    assert pending == [
        _worker(),
        _worker(
            worker_id="W-2",
            workspace_id="WS-2",
            tenant="noxus",
            use_case_id=None,
            updated_at=date(2026, 7, 26),
            agent_name=None,
            agent_description=None,
            agent_owner=None,
            provider_version_id=None,
        ),
    ]
    assert "resolved_at IS NULL" in conn.fetch_calls[0][0]
