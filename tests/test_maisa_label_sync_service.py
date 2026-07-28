from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.models.use_case_label import UseCaseLabel
from sinc_amn.repositories.use_case_label_repository import UseCaseLabelRepository
from sinc_amn.services.maisa_label_sync_service import MaisaLabelSyncService


def _label(**overrides) -> UseCaseLabel:
    now = datetime.now(timezone.utc)
    data = dict(
        id=uuid4(),
        source_resource_id="RES-1",
        name="Caso 1",
        name_lower="caso 1",
        organization_id="org-1",
        worker_count=0,
        status="new",
        maisa_label_id=None,
        created_at=now,
        updated_at=now,
    )
    data.update(overrides)
    return UseCaseLabel(**data)


async def test_run_creates_new_labels_and_marks_synced():
    new_label = _label()
    repo = AsyncMock(spec=UseCaseLabelRepository)
    repo.get_pending_for_maisa.return_value = [new_label]
    maisa = AsyncMock(spec=MaisaClient)
    maisa.create_label.return_value = "maisa-generated-id"

    service = MaisaLabelSyncService(use_case_labels=repo, maisa=maisa)
    await service.run()

    maisa.create_label.assert_awaited_once_with(new_label)
    maisa.update_label.assert_not_awaited()
    repo.mark_synced.assert_awaited_once_with(
        new_label.id, "maisa-generated-id", expected_status="new"
    )


async def test_run_updates_existing_labels_and_marks_synced():
    existing_label = _label(status="modified", maisa_label_id="maisa-existing")
    repo = AsyncMock(spec=UseCaseLabelRepository)
    repo.get_pending_for_maisa.return_value = [existing_label]
    maisa = AsyncMock(spec=MaisaClient)

    service = MaisaLabelSyncService(use_case_labels=repo, maisa=maisa)
    await service.run()

    maisa.update_label.assert_awaited_once_with("maisa-existing", existing_label)
    maisa.create_label.assert_not_awaited()
    repo.mark_synced.assert_awaited_once_with(
        existing_label.id, "maisa-existing", expected_status="modified"
    )


async def test_run_with_no_pending_labels_does_nothing():
    repo = AsyncMock(spec=UseCaseLabelRepository)
    repo.get_pending_for_maisa.return_value = []
    maisa = AsyncMock(spec=MaisaClient)

    service = MaisaLabelSyncService(use_case_labels=repo, maisa=maisa)
    await service.run()

    maisa.create_label.assert_not_awaited()
    maisa.update_label.assert_not_awaited()
    repo.mark_synced.assert_not_awaited()
