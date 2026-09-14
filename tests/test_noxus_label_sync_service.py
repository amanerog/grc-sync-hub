from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.models.noxus_use_case_label import NoxusUseCaseLabel
from sinc_amn.repositories.noxus_use_case_label_repository import (
    NoxusUseCaseLabelRepository,
)
from sinc_amn.services.noxus_label_sync_service import NoxusLabelSyncService


def _label(**overrides) -> NoxusUseCaseLabel:
    now = datetime.now(timezone.utc)
    data = dict(
        id=uuid4(),
        source_resource_id="RES-1",
        name="Caso 1",
        name_lower="caso 1",
        organization_id="org-1",
        worker_count=0,
        status="new",
        noxus_label_id=None,
        created_at=now,
        updated_at=now,
    )
    data.update(overrides)
    return NoxusUseCaseLabel(**data)


async def test_run_creates_new_labels_and_marks_synced():
    new_label = _label()
    repo = AsyncMock(spec=NoxusUseCaseLabelRepository)
    repo.get_pending_for_noxus.return_value = [new_label]
    noxus = AsyncMock(spec=NoxusClient)
    noxus.create_label.return_value = "noxus-generated-id"

    service = NoxusLabelSyncService(use_case_labels=repo, noxus=noxus)
    summary = await service.run()

    noxus.create_label.assert_awaited_once_with(new_label)
    noxus.update_label.assert_not_awaited()
    repo.mark_synced.assert_awaited_once_with(
        new_label.id, "noxus-generated-id", expected_status="new"
    )
    assert summary == {"total": 1, "succeeded": 1, "failed": 0}


async def test_run_updates_existing_labels_and_marks_synced():
    existing_label = _label(status="modified", noxus_label_id="noxus-existing")
    repo = AsyncMock(spec=NoxusUseCaseLabelRepository)
    repo.get_pending_for_noxus.return_value = [existing_label]
    noxus = AsyncMock(spec=NoxusClient)

    service = NoxusLabelSyncService(use_case_labels=repo, noxus=noxus)
    summary = await service.run()

    noxus.update_label.assert_awaited_once_with("noxus-existing", existing_label)
    noxus.create_label.assert_not_awaited()
    repo.mark_synced.assert_awaited_once_with(
        existing_label.id, "noxus-existing", expected_status="modified"
    )
    assert summary == {"total": 1, "succeeded": 1, "failed": 0}


async def test_run_with_no_pending_labels_does_nothing():
    repo = AsyncMock(spec=NoxusUseCaseLabelRepository)
    repo.get_pending_for_noxus.return_value = []
    noxus = AsyncMock(spec=NoxusClient)

    service = NoxusLabelSyncService(use_case_labels=repo, noxus=noxus)
    summary = await service.run()

    noxus.create_label.assert_not_awaited()
    noxus.update_label.assert_not_awaited()
    repo.mark_synced.assert_not_awaited()
    assert summary == {"total": 0, "succeeded": 0, "failed": 0}


async def test_run_isolates_failure_and_keeps_processing_rest_of_batch():
    failing_label = _label(source_resource_id="RES-1")
    ok_label = _label(source_resource_id="RES-2")
    repo = AsyncMock(spec=NoxusUseCaseLabelRepository)
    repo.get_pending_for_noxus.return_value = [failing_label, ok_label]
    noxus = AsyncMock(spec=NoxusClient)
    noxus.create_label.side_effect = [RuntimeError("boom"), "noxus-generated-id"]

    service = NoxusLabelSyncService(use_case_labels=repo, noxus=noxus)
    summary = await service.run()

    # El fallo en el primer label no impide procesar (y marcar synced) el segundo.
    repo.mark_synced.assert_awaited_once_with(
        ok_label.id, "noxus-generated-id", expected_status=ok_label.status
    )
    assert summary == {"total": 2, "succeeded": 1, "failed": 1}
