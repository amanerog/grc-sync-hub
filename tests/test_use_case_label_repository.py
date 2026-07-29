from datetime import datetime, timezone
from uuid import uuid4

from sinc_amn.models.use_case import UseCase
from sinc_amn.repositories.use_case_label_repository import UseCaseLabelRepository


class FakeConnection:
    def __init__(self, fetchrow_results=None, fetch_result=None):
        self.fetchrow_results = list(fetchrow_results or [])
        self.fetch_result = fetch_result or []
        self.fetchrow_calls: list[tuple] = []
        self.fetch_calls: list[tuple] = []
        self.execute_calls: list[tuple] = []

    async def fetchrow(self, query, *args):
        self.fetchrow_calls.append((query, args))
        return self.fetchrow_results.pop(0) if self.fetchrow_results else None

    async def fetch(self, query, *args):
        self.fetch_calls.append((query, args))
        return self.fetch_result

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))


class _AcquireContext:
    def __init__(self, conn: FakeConnection):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc_info):
        return False


class FakePool:
    def __init__(self, conn: FakeConnection):
        self.conn = conn

    def acquire(self):
        return _AcquireContext(self.conn)


def _label_row(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    row = {
        "id": uuid4(),
        "source_resource_id": "RES-1",
        "name": "Caso 1",
        "name_lower": "caso 1",
        "entity": "AI System",
        "organization_id": "org-1",
        "worker_count": 0,
        "status": "new",
        "maisa_label_id": None,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
        "is_deleted": False,
    }
    row.update(overrides)
    return row


async def test_upsert_from_use_case_inserts_when_new():
    conn = FakeConnection(fetchrow_results=[None, _label_row()])
    repo = UseCaseLabelRepository(FakePool(conn))
    use_case = UseCase(
        resource_id="RES-1",
        name="Caso 1",
        tenant="maisa",
        entity="AI System",
        updated_at=datetime.now(timezone.utc),
    )

    label = await repo.upsert_from_use_case(use_case, organization_id="org-1")

    assert label.source_resource_id == "RES-1"
    assert label.status == "new"
    assert len(conn.fetchrow_calls) == 2
    assert "INSERT INTO" in conn.fetchrow_calls[1][0]
    assert "AI System" in conn.fetchrow_calls[1][1]


async def test_upsert_from_use_case_updates_when_existing():
    existing_id = uuid4()
    conn = FakeConnection(
        fetchrow_results=[
            _label_row(id=existing_id),
            _label_row(
                id=existing_id,
                status="modified",
                name="Caso 1 renombrado",
                entity="Non-AI System",
            ),
        ]
    )
    repo = UseCaseLabelRepository(FakePool(conn))
    use_case = UseCase(
        resource_id="RES-1",
        name="Caso 1 renombrado",
        tenant="maisa",
        entity="Non-AI System",
        updated_at=datetime.now(timezone.utc),
    )

    label = await repo.upsert_from_use_case(use_case, organization_id="org-1")

    assert label.status == "modified"
    assert label.name == "Caso 1 renombrado"
    assert label.entity == "Non-AI System"
    assert "UPDATE maisa_use_case_labels" in conn.fetchrow_calls[1][0]
    assert "Non-AI System" in conn.fetchrow_calls[1][1]


async def test_get_pending_for_maisa_returns_labels():
    conn = FakeConnection(fetch_result=[_label_row(), _label_row(status="modified")])
    repo = UseCaseLabelRepository(FakePool(conn))

    labels = await repo.get_pending_for_maisa(organization_id="org-1")

    assert len(labels) == 2
    assert {label.status for label in labels} == {"new", "modified"}


async def test_mark_synced_executes_update_with_expected_args():
    conn = FakeConnection()
    repo = UseCaseLabelRepository(FakePool(conn))
    label_id = uuid4()

    await repo.mark_synced(label_id, maisa_label_id="maisa-1", expected_status="new")

    assert len(conn.execute_calls) == 1
    _, args = conn.execute_calls[0]
    assert args[0] == "maisa-1"
    assert args[2] == label_id
    assert args[3] == "new"
