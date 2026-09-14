from datetime import datetime, timezone
from unittest.mock import AsyncMock

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.models.use_case import UseCase
from sinc_amn.repositories.noxus_use_case_label_repository import (
    NoxusUseCaseLabelRepository,
)
from sinc_amn.repositories.use_case_label_repository import UseCaseLabelRepository
from sinc_amn.repositories.use_case_sync_failure_repository import (
    UseCaseSyncFailureRepository,
)
from sinc_amn.services.use_case_sync_service import UseCaseSyncService


def _use_case(**overrides) -> UseCase:
    data = dict(
        resource_id="RES-1",
        name="Caso 1",
        tenant="maisa",
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    data.update(overrides)
    return UseCase(**data)


def _service(
    auron=None, use_case_labels=None, noxus_use_case_labels=None, sync_failures=None
):
    return UseCaseSyncService(
        auron=auron or AsyncMock(spec=AuronClient),
        use_case_labels=use_case_labels or AsyncMock(spec=UseCaseLabelRepository),
        noxus_use_case_labels=noxus_use_case_labels
        or AsyncMock(spec=NoxusUseCaseLabelRepository),
        sync_failures=sync_failures,
    )


async def test_run_routes_use_cases_by_tenant():
    maisa_uc = _use_case(resource_id="RES-1", tenant="maisa")
    noxus_uc = _use_case(resource_id="RES-2", tenant="noxus")

    auron = AsyncMock(spec=AuronClient)
    auron.get_use_cases.return_value = [maisa_uc, noxus_uc]
    use_case_labels = AsyncMock(spec=UseCaseLabelRepository)
    noxus_use_case_labels = AsyncMock(spec=NoxusUseCaseLabelRepository)
    sync_failures = AsyncMock(spec=UseCaseSyncFailureRepository)
    sync_failures.get_pending.return_value = []

    service = _service(
        auron=auron,
        use_case_labels=use_case_labels,
        noxus_use_case_labels=noxus_use_case_labels,
        sync_failures=sync_failures,
    )
    summary = await service.run()

    auron.get_use_cases.assert_awaited_once_with(tenants=["maisa", "noxus"])
    use_case_labels.upsert_from_use_case.assert_awaited_once()
    noxus_use_case_labels.upsert_from_use_case.assert_awaited_once()
    sync_failures.mark_resolved.assert_any_await("RES-1")
    sync_failures.mark_resolved.assert_any_await("RES-2")
    sync_failures.record_failure.assert_not_awaited()
    assert summary == {"total": 2, "succeeded": 2, "failed": 0}


async def test_run_with_no_use_cases_does_nothing():
    auron = AsyncMock(spec=AuronClient)
    auron.get_use_cases.return_value = []
    use_case_labels = AsyncMock(spec=UseCaseLabelRepository)
    noxus_use_case_labels = AsyncMock(spec=NoxusUseCaseLabelRepository)
    sync_failures = AsyncMock(spec=UseCaseSyncFailureRepository)
    sync_failures.get_pending.return_value = []

    service = _service(
        auron=auron,
        use_case_labels=use_case_labels,
        noxus_use_case_labels=noxus_use_case_labels,
        sync_failures=sync_failures,
    )
    summary = await service.run()

    use_case_labels.upsert_from_use_case.assert_not_awaited()
    noxus_use_case_labels.upsert_from_use_case.assert_not_awaited()
    assert summary == {"total": 0, "succeeded": 0, "failed": 0}


async def test_run_isolates_failure_and_keeps_processing_rest_of_batch():
    failing_uc = _use_case(resource_id="RES-1", tenant="maisa")
    ok_uc = _use_case(resource_id="RES-2", tenant="noxus")

    auron = AsyncMock(spec=AuronClient)
    auron.get_use_cases.return_value = [failing_uc, ok_uc]
    use_case_labels = AsyncMock(spec=UseCaseLabelRepository)
    use_case_labels.upsert_from_use_case.side_effect = RuntimeError("boom")
    noxus_use_case_labels = AsyncMock(spec=NoxusUseCaseLabelRepository)
    sync_failures = AsyncMock(spec=UseCaseSyncFailureRepository)
    sync_failures.get_pending.return_value = []

    service = _service(
        auron=auron,
        use_case_labels=use_case_labels,
        noxus_use_case_labels=noxus_use_case_labels,
        sync_failures=sync_failures,
    )
    summary = await service.run()

    # El fallo en el item Maisa no impide procesar el item Noxus siguiente.
    noxus_use_case_labels.upsert_from_use_case.assert_awaited_once()
    sync_failures.record_failure.assert_awaited_once_with("RES-1", "maisa", "boom")
    sync_failures.mark_resolved.assert_awaited_once_with("RES-2")
    assert summary == {"total": 2, "succeeded": 1, "failed": 1}


async def test_run_retries_pending_failures_by_resource_id():
    auron = AsyncMock(spec=AuronClient)
    auron.get_use_cases.return_value = []
    retried_uc = _use_case(resource_id="RES-OLD", tenant="maisa")
    auron.get_use_cases_by_resource_ids.return_value = [retried_uc]
    use_case_labels = AsyncMock(spec=UseCaseLabelRepository)
    noxus_use_case_labels = AsyncMock(spec=NoxusUseCaseLabelRepository)
    sync_failures = AsyncMock(spec=UseCaseSyncFailureRepository)
    sync_failures.get_pending.return_value = [
        {"resource_id": "RES-OLD", "tenant": "maisa"}
    ]

    service = _service(
        auron=auron,
        use_case_labels=use_case_labels,
        noxus_use_case_labels=noxus_use_case_labels,
        sync_failures=sync_failures,
    )
    summary = await service.run()

    auron.get_use_cases_by_resource_ids.assert_awaited_once_with(
        ["RES-OLD"], "maisa"
    )
    use_case_labels.upsert_from_use_case.assert_awaited_once()
    sync_failures.mark_resolved.assert_awaited_once_with("RES-OLD")
    assert summary == {"total": 1, "succeeded": 1, "failed": 0}


async def test_run_isolates_sync_failures_tracking_error_too():
    # record_failure/mark_resolved son en si mismos auxiliares - un fallo
    # ahi tampoco debe tumbar el aislamiento del item.
    ok_uc = _use_case(resource_id="RES-1", tenant="maisa")

    auron = AsyncMock(spec=AuronClient)
    auron.get_use_cases.return_value = [ok_uc]
    use_case_labels = AsyncMock(spec=UseCaseLabelRepository)
    noxus_use_case_labels = AsyncMock(spec=NoxusUseCaseLabelRepository)
    sync_failures = AsyncMock(spec=UseCaseSyncFailureRepository)
    sync_failures.get_pending.return_value = []
    sync_failures.mark_resolved.side_effect = RuntimeError("db blip")

    service = _service(
        auron=auron,
        use_case_labels=use_case_labels,
        noxus_use_case_labels=noxus_use_case_labels,
        sync_failures=sync_failures,
    )
    summary = await service.run()

    use_case_labels.upsert_from_use_case.assert_awaited_once()
    assert summary == {"total": 1, "succeeded": 1, "failed": 0}


async def test_run_with_no_pending_failures_skips_retry():
    auron = AsyncMock(spec=AuronClient)
    auron.get_use_cases.return_value = []
    sync_failures = AsyncMock(spec=UseCaseSyncFailureRepository)
    sync_failures.get_pending.return_value = []

    service = _service(auron=auron, sync_failures=sync_failures)
    await service.run()

    auron.get_use_cases_by_resource_ids.assert_not_awaited()
