from sinc_amn.repositories.use_case_sync_failure_repository import (
    UseCaseSyncFailureRepository,
)

from ._asyncpg_fakes import FakeConnection, FakePool


async def test_record_failure_executes_upsert_with_expected_args():
    conn = FakeConnection()
    repo = UseCaseSyncFailureRepository(FakePool(conn))

    await repo.record_failure("RES-1", tenant="maisa", error="boom")

    assert len(conn.execute_calls) == 1
    query, args = conn.execute_calls[0]
    assert "INSERT INTO use_case_sync_failures" in query
    assert "ON CONFLICT" in query
    assert args[0] == "RES-1"
    assert args[1] == "maisa"
    assert args[2] == "boom"


async def test_mark_resolved_executes_update_with_resource_id():
    conn = FakeConnection()
    repo = UseCaseSyncFailureRepository(FakePool(conn))

    await repo.mark_resolved("RES-1")

    assert len(conn.execute_calls) == 1
    query, args = conn.execute_calls[0]
    assert "UPDATE use_case_sync_failures" in query
    assert args[0] == "RES-1"


async def test_get_pending_returns_resource_id_and_tenant():
    conn = FakeConnection(
        fetch_result=[
            {"resource_id": "RES-1", "tenant": "maisa"},
            {"resource_id": "RES-2", "tenant": "noxus"},
        ]
    )
    repo = UseCaseSyncFailureRepository(FakePool(conn))

    pending = await repo.get_pending()

    assert pending == [
        {"resource_id": "RES-1", "tenant": "maisa"},
        {"resource_id": "RES-2", "tenant": "noxus"},
    ]
    assert "resolved_at IS NULL" in conn.fetch_calls[0][0]
