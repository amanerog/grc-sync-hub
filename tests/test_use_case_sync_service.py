from datetime import datetime, timezone
from unittest.mock import AsyncMock

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.models.use_case import UseCase
from sinc_amn.repositories.use_case_label_repository import UseCaseLabelRepository
from sinc_amn.services.use_case_sync_service import UseCaseSyncService


def _use_case(**overrides) -> UseCase:
    data = dict(
        resource_id="RES-1",
        name="Caso 1",
        tenant="maisa",
        updated_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    data.update(overrides)
    return UseCase(**data)


async def test_run_routes_use_cases_by_tenant():
    maisa_uc = _use_case(resource_id="RES-1", tenant="maisa")
    noxus_uc = _use_case(resource_id="RES-2", tenant="noxus")

    auron = AsyncMock(spec=AuronClient)
    auron.get_use_cases.return_value = [maisa_uc, noxus_uc]
    use_case_labels = AsyncMock(spec=UseCaseLabelRepository)
    noxus = AsyncMock(spec=NoxusClient)

    service = UseCaseSyncService(auron, use_case_labels, noxus)
    await service.run()

    auron.get_use_cases.assert_awaited_once_with(tenants=["maisa", "noxus"])
    use_case_labels.upsert_from_use_case.assert_awaited_once()
    noxus.push_use_case.assert_awaited_once_with(noxus_uc)


async def test_run_with_no_use_cases_does_nothing():
    auron = AsyncMock(spec=AuronClient)
    auron.get_use_cases.return_value = []
    use_case_labels = AsyncMock(spec=UseCaseLabelRepository)
    noxus = AsyncMock(spec=NoxusClient)

    service = UseCaseSyncService(auron, use_case_labels, noxus)
    await service.run()

    use_case_labels.upsert_from_use_case.assert_not_awaited()
    noxus.push_use_case.assert_not_awaited()
