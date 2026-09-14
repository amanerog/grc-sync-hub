from datetime import datetime, timezone
from uuid import uuid4

from sinc_amn.models.use_case import UseCase
from sinc_amn.repositories.noxus_use_case_label_repository import (
    NoxusUseCaseLabelRepository,
)

from ._asyncpg_fakes import FakeConnection, FakePool


def _label_row(**overrides) -> dict:
    now = datetime.now(timezone.utc)
    row = {
        "id": uuid4(),
        "source_resource_id": "RES-1",
        "name": "Caso 1",
        "name_lower": "caso 1",
        "entity": "AI System",
        "owner": "owner@example.com",
        "workspace_id": "WS-1",
        "organization_id": "org-1",
        "worker_count": 0,
        "status": "new",
        "noxus_label_id": None,
        "created_at": now,
        "updated_at": now,
        "deleted_at": None,
        "is_deleted": False,
    }
    row.update(overrides)
    return row


async def test_upsert_from_use_case_inserts_when_new():
    conn = FakeConnection(fetchrow_results=[None, _label_row(workspace_id=None)])
    repo = NoxusUseCaseLabelRepository(FakePool(conn))
    use_case = UseCase(
        resource_id="RES-1",
        name="Caso 1",
        tenant="noxus",
        entity="AI System",
        owner="owner@example.com",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    label = await repo.upsert_from_use_case(use_case, organization_id="org-1")

    assert label.source_resource_id == "RES-1"
    assert label.status == "new"
    assert label.owner == "owner@example.com"
    assert label.workspace_id is None
    assert len(conn.fetchrow_calls) == 2
    assert "INSERT INTO" in conn.fetchrow_calls[1][0]
    assert "AI System" in conn.fetchrow_calls[1][1]
    assert "owner@example.com" in conn.fetchrow_calls[1][1]
    # workspace_id no se pasa: la ingesta desde Flujo 1 no lo trae de OpenPages.
    assert conn.fetchrow_calls[1][1][6] is None


async def test_upsert_from_use_case_inserts_with_explicit_workspace_id():
    conn = FakeConnection(fetchrow_results=[None, _label_row(workspace_id="WS-1")])
    repo = NoxusUseCaseLabelRepository(FakePool(conn))
    use_case = UseCase(
        resource_id="RES-1",
        name="Caso 1",
        tenant="noxus",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    label = await repo.upsert_from_use_case(
        use_case, organization_id="org-1", workspace_id="WS-1"
    )

    assert label.workspace_id == "WS-1"
    assert conn.fetchrow_calls[1][1][6] == "WS-1"


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
                owner="new-owner@example.com",
            ),
        ]
    )
    repo = NoxusUseCaseLabelRepository(FakePool(conn))
    use_case = UseCase(
        resource_id="RES-1",
        name="Caso 1 renombrado",
        tenant="noxus",
        entity="Non-AI System",
        owner="new-owner@example.com",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    label = await repo.upsert_from_use_case(use_case, organization_id="org-1")

    assert label.status == "modified"
    assert label.name == "Caso 1 renombrado"
    assert label.entity == "Non-AI System"
    assert label.owner == "new-owner@example.com"
    assert "UPDATE noxus_use_case_labels" in conn.fetchrow_calls[1][0]
    assert "Non-AI System" in conn.fetchrow_calls[1][1]
    assert "new-owner@example.com" in conn.fetchrow_calls[1][1]
    # Sin workspace_id explicito, el UPDATE lo pasa como None -> el COALESCE
    # del lado SQL es quien evita pisar el valor ya guardado.
    assert conn.fetchrow_calls[1][1][4] is None


async def test_upsert_from_use_case_update_passes_explicit_workspace_id():
    existing_id = uuid4()
    conn = FakeConnection(
        fetchrow_results=[
            _label_row(id=existing_id, workspace_id="WS-1"),
            _label_row(id=existing_id, status="modified", workspace_id="WS-2"),
        ]
    )
    repo = NoxusUseCaseLabelRepository(FakePool(conn))
    use_case = UseCase(
        resource_id="RES-1",
        name="Caso 1",
        tenant="noxus",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    label = await repo.upsert_from_use_case(
        use_case, organization_id="org-1", workspace_id="WS-2"
    )

    assert label.workspace_id == "WS-2"
    assert conn.fetchrow_calls[1][1][4] == "WS-2"


async def test_get_by_resource_id_returns_label_when_found():
    conn = FakeConnection(fetchrow_results=[_label_row()])
    repo = NoxusUseCaseLabelRepository(FakePool(conn))

    label = await repo.get_by_resource_id("RES-1", organization_id="org-1")

    assert label is not None
    assert label.source_resource_id == "RES-1"
    assert label.owner == "owner@example.com"
    assert conn.fetchrow_calls[0][1] == ("org-1", "RES-1")


async def test_get_by_resource_id_returns_none_when_not_found():
    conn = FakeConnection(fetchrow_results=[None])
    repo = NoxusUseCaseLabelRepository(FakePool(conn))

    label = await repo.get_by_resource_id("RES-404", organization_id="org-1")

    assert label is None


async def test_get_pending_for_noxus_returns_labels():
    conn = FakeConnection(fetch_result=[_label_row(), _label_row(status="modified")])
    repo = NoxusUseCaseLabelRepository(FakePool(conn))

    labels = await repo.get_pending_for_noxus(organization_id="org-1")

    assert len(labels) == 2
    assert {label.status for label in labels} == {"new", "modified"}


async def test_mark_synced_executes_update_with_expected_args():
    conn = FakeConnection()
    repo = NoxusUseCaseLabelRepository(FakePool(conn))
    label_id = uuid4()

    await repo.mark_synced(label_id, noxus_label_id="noxus-1", expected_status="new")

    assert len(conn.execute_calls) == 1
    _, args = conn.execute_calls[0]
    assert args[0] == "noxus-1"
    assert args[2] == label_id
    assert args[3] == "new"
