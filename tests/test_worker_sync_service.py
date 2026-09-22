from datetime import date, datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.config import settings
from sinc_amn.core.monitoring import MonitoringStore
from sinc_amn.core.notifications import AdminNotifier
from sinc_amn.models.noxus_use_case_label import NoxusUseCaseLabel
from sinc_amn.models.use_case_label import UseCaseLabel
from sinc_amn.models.worker import Worker
from sinc_amn.repositories.noxus_use_case_label_repository import (
    NoxusUseCaseLabelRepository,
)
from sinc_amn.repositories.use_case_label_repository import UseCaseLabelRepository
from sinc_amn.repositories.worker_sync_failure_repository import (
    WorkerSyncFailureRepository,
)
from sinc_amn.services.worker_sync_service import WorkerSyncService


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
    )
    data.update(overrides)
    return Worker(**data)


def _service(
    auron=None, maisa=None, noxus=None, monitoring=None, notifier=None,
    use_case_labels=None, noxus_use_case_labels=None, sync_failures=None,
):
    if use_case_labels is None:
        # Por defecto no hay owner en la tabla intermedia (los tests que lo
        # necesiten pasan su propio mock ya configurado).
        use_case_labels = AsyncMock(spec=UseCaseLabelRepository)
        use_case_labels.get_by_resource_id.return_value = None
    if noxus_use_case_labels is None:
        noxus_use_case_labels = AsyncMock(spec=NoxusUseCaseLabelRepository)
        noxus_use_case_labels.get_by_resource_id.return_value = None
    if sync_failures is None:
        sync_failures = AsyncMock(spec=WorkerSyncFailureRepository)
        sync_failures.get_pending.return_value = []
    return WorkerSyncService(
        auron=auron or AsyncMock(spec=AuronClient),
        maisa=maisa or AsyncMock(spec=MaisaClient),
        noxus=noxus or AsyncMock(spec=NoxusClient),
        monitoring=monitoring or AsyncMock(spec=MonitoringStore),
        notifier=notifier or AsyncMock(spec=AdminNotifier),
        use_case_labels=use_case_labels,
        noxus_use_case_labels=noxus_use_case_labels,
        sync_failures=sync_failures,
    )


async def test_run_combines_maisa_and_noxus_workers_and_updates_existing_agent():
    worker = _worker()
    maisa = AsyncMock(spec=MaisaClient)
    maisa.get_updated_workers.return_value = [worker]
    noxus = AsyncMock(spec=NoxusClient)
    noxus.get_updated_workers.return_value = []
    auron = AsyncMock(spec=AuronClient)
    # El caso de uso vinculado (primaryParentId) ya coincide con el del
    # worker - toma la rama update_agent, no borrar+recrear.
    auron.get_agent_by_worker_id.return_value = {
        "id": "agent-1",
        "primaryParentId": "UC-1",
    }
    monitoring = AsyncMock(spec=MonitoringStore)

    service = _service(auron=auron, maisa=maisa, noxus=noxus, monitoring=monitoring)
    summary = await service.run()

    auron.update_agent.assert_awaited_once_with(
        agent_id="agent-1",
        tenant="maisa",
        name="Agente de prueba",
        description="Descripcion de prueba",
        use_case_owner=None,
        agent_owner="agent-owner@example.com",
        provider_version_id=None,
    )
    auron.create_agent.assert_not_awaited()
    auron.dissociate.assert_not_awaited()
    auron.associate.assert_not_awaited()
    monitoring.record.assert_awaited_once()
    assert summary == {"total": 1, "succeeded": 1, "failed": 0}


async def test_ingest_worker_reassociates_when_use_case_changed():
    worker = _worker(use_case_id="UC-2")
    auron = AsyncMock(spec=AuronClient)
    # El Agent ya existia vinculado a otro caso de uso (UC-1) - no se puede
    # reasignar via update_agent (confirmado), hay que borrar la asociacion
    # vieja y crear la nueva (sin borrar/recrear el Agent entero).
    auron.get_agent_by_worker_id.return_value = {
        "id": "agent-1",
        "primaryParentId": "UC-1",
    }
    auron.update_agent.return_value = {"id": "agent-1"}

    service = _service(auron=auron)
    ok = await service._ingest_worker(worker)

    assert ok is True
    auron.dissociate.assert_awaited_once_with("agent-1", "UC-1")
    auron.associate.assert_awaited_once_with(
        "agent-1", "UC-2", association_definition_id="966", association_type="PARENT"
    )
    auron.update_agent.assert_awaited_once_with(
        agent_id="agent-1",
        tenant="maisa",
        name="Agente de prueba",
        description="Descripcion de prueba",
        use_case_owner=None,
        agent_owner="agent-owner@example.com",
        provider_version_id=None,
    )
    auron.create_agent.assert_not_awaited()


async def test_ingest_worker_isolates_failure_when_reassociation_fails():
    worker = _worker(use_case_id="UC-2")
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = {
        "id": "agent-1",
        "primaryParentId": "UC-1",
    }
    auron.dissociate.side_effect = RuntimeError("boom")

    service = _service(auron=auron)
    ok = await service._ingest_worker(worker)

    assert ok is False
    auron.associate.assert_not_awaited()
    auron.update_agent.assert_not_awaited()
    auron.create_agent.assert_not_awaited()


async def test_run_looks_up_use_case_owner_from_intermediate_table():
    worker = _worker()
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.return_value = {"id": "new-agent"}
    use_case_labels = AsyncMock(spec=UseCaseLabelRepository)
    use_case_labels.get_by_resource_id.return_value = UseCaseLabel(
        id=uuid4(),
        source_resource_id="UC-1",
        name="Caso 1",
        name_lower="caso 1",
        owner="use-case-owner@example.com",
        organization_id="org-1",
        worker_count=0,
        status="synced",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    service = _service(auron=auron, use_case_labels=use_case_labels)
    await service._ingest_worker(worker)

    use_case_labels.get_by_resource_id.assert_awaited_once_with(
        "UC-1", organization_id=settings.maisa_organization_id
    )
    auron.create_agent.assert_awaited_once_with(
        worker_id="W-1",
        use_case_id="UC-1",
        tenant="maisa",
        name="Agente de prueba",
        description="Descripcion de prueba",
        use_case_owner="use-case-owner@example.com",
        agent_owner="agent-owner@example.com",
        provider_version_id=None,
    )


async def test_run_looks_up_use_case_owner_from_noxus_intermediate_table():
    worker = _worker(tenant="noxus")
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.return_value = {"id": "new-agent"}
    use_case_labels = AsyncMock(spec=UseCaseLabelRepository)
    noxus_use_case_labels = AsyncMock(spec=NoxusUseCaseLabelRepository)
    noxus_use_case_labels.get_by_resource_id.return_value = NoxusUseCaseLabel(
        id=uuid4(),
        source_resource_id="UC-1",
        name="Caso 1",
        name_lower="caso 1",
        owner="noxus-owner@example.com",
        organization_id="org-1",
        worker_count=0,
        status="synced",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    service = _service(
        auron=auron,
        use_case_labels=use_case_labels,
        noxus_use_case_labels=noxus_use_case_labels,
    )
    await service._ingest_worker(worker)

    noxus_use_case_labels.get_by_resource_id.assert_awaited_once_with(
        "UC-1", organization_id=settings.noxus_organization_id
    )
    use_case_labels.get_by_resource_id.assert_not_awaited()
    auron.create_agent.assert_awaited_once_with(
        worker_id="W-1",
        use_case_id="UC-1",
        tenant="noxus",
        name="Agente de prueba",
        description="Descripcion de prueba",
        use_case_owner="noxus-owner@example.com",
        agent_owner="agent-owner@example.com",
        provider_version_id=None,
    )


async def test_ingest_worker_backfills_workspace_id_when_missing_on_noxus_label():
    worker = _worker(tenant="noxus", workspace_id="WS-1")
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.return_value = {"id": "new-agent"}
    noxus_use_case_labels = AsyncMock(spec=NoxusUseCaseLabelRepository)
    noxus_use_case_labels.get_by_resource_id.return_value = NoxusUseCaseLabel(
        id=uuid4(),
        source_resource_id="UC-1",
        name="Caso 1",
        name_lower="caso 1",
        workspace_id=None,
        organization_id="org-1",
        worker_count=0,
        status="synced",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    service = _service(auron=auron, noxus_use_case_labels=noxus_use_case_labels)
    await service._ingest_worker(worker)

    noxus_use_case_labels.set_workspace_id_if_missing.assert_awaited_once_with(
        "UC-1", organization_id=settings.noxus_organization_id, workspace_id="WS-1"
    )


async def test_ingest_worker_skips_workspace_id_backfill_when_already_set():
    worker = _worker(tenant="noxus", workspace_id="WS-1")
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.return_value = {"id": "new-agent"}
    noxus_use_case_labels = AsyncMock(spec=NoxusUseCaseLabelRepository)
    noxus_use_case_labels.get_by_resource_id.return_value = NoxusUseCaseLabel(
        id=uuid4(),
        source_resource_id="UC-1",
        name="Caso 1",
        name_lower="caso 1",
        workspace_id="WS-ALREADY-SET",
        organization_id="org-1",
        worker_count=0,
        status="synced",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    service = _service(auron=auron, noxus_use_case_labels=noxus_use_case_labels)
    await service._ingest_worker(worker)

    noxus_use_case_labels.set_workspace_id_if_missing.assert_not_awaited()


async def test_ingest_worker_isolates_workspace_id_backfill_failure():
    worker = _worker(tenant="noxus", workspace_id="WS-1")
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.return_value = {"id": "new-agent"}
    noxus_use_case_labels = AsyncMock(spec=NoxusUseCaseLabelRepository)
    noxus_use_case_labels.get_by_resource_id.return_value = NoxusUseCaseLabel(
        id=uuid4(),
        source_resource_id="UC-1",
        name="Caso 1",
        name_lower="caso 1",
        workspace_id=None,
        organization_id="org-1",
        worker_count=0,
        status="synced",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    noxus_use_case_labels.set_workspace_id_if_missing.side_effect = RuntimeError(
        "db blip"
    )

    service = _service(auron=auron, noxus_use_case_labels=noxus_use_case_labels)
    ok = await service._ingest_worker(worker)

    assert ok is True
    auron.create_agent.assert_awaited_once()


async def test_ingest_worker_passes_provider_version_id_through_to_create_agent():
    worker = _worker(provider_version_id="v2.1")
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.return_value = {"id": "new-agent"}

    service = _service(auron=auron)
    await service._ingest_worker(worker)

    auron.create_agent.assert_awaited_once_with(
        worker_id="W-1",
        use_case_id="UC-1",
        tenant="maisa",
        name="Agente de prueba",
        description="Descripcion de prueba",
        use_case_owner=None,
        agent_owner="agent-owner@example.com",
        provider_version_id="v2.1",
    )


async def test_run_isolates_failure_and_keeps_processing_rest_of_batch():
    failing_worker = _worker(worker_id="W-1")
    ok_worker = _worker(worker_id="W-2")
    maisa = AsyncMock(spec=MaisaClient)
    maisa.get_updated_workers.return_value = [failing_worker, ok_worker]
    noxus = AsyncMock(spec=NoxusClient)
    noxus.get_updated_workers.return_value = []
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.side_effect = [RuntimeError("boom"), None]
    auron.create_agent.return_value = {"id": "new-agent"}
    monitoring = AsyncMock(spec=MonitoringStore)

    service = _service(auron=auron, maisa=maisa, noxus=noxus, monitoring=monitoring)
    summary = await service.run()

    # El fallo en el primer worker no impide procesar (y crear el agente de) el segundo.
    auron.create_agent.assert_awaited_once_with(
        worker_id="W-2",
        use_case_id="UC-1",
        tenant="maisa",
        name="Agente de prueba",
        description="Descripcion de prueba",
        use_case_owner=None,
        agent_owner="agent-owner@example.com",
        provider_version_id=None,
    )
    assert summary == {"total": 2, "succeeded": 1, "failed": 1}


async def test_run_retries_pending_worker_failures():
    maisa = AsyncMock(spec=MaisaClient)
    maisa.get_updated_workers.return_value = []
    noxus = AsyncMock(spec=NoxusClient)
    noxus.get_updated_workers.return_value = []
    retried_worker = _worker(worker_id="W-OLD")
    sync_failures = AsyncMock(spec=WorkerSyncFailureRepository)
    sync_failures.get_pending.return_value = [retried_worker]
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.return_value = {"id": "new-agent"}

    service = _service(
        auron=auron, maisa=maisa, noxus=noxus, sync_failures=sync_failures
    )
    summary = await service.run()

    auron.create_agent.assert_awaited_once_with(
        worker_id="W-OLD",
        use_case_id="UC-1",
        tenant="maisa",
        name="Agente de prueba",
        description="Descripcion de prueba",
        use_case_owner=None,
        agent_owner="agent-owner@example.com",
        provider_version_id=None,
    )
    sync_failures.mark_resolved.assert_awaited_once_with("W-OLD")
    assert summary == {"total": 1, "succeeded": 1, "failed": 0}


async def test_run_with_no_pending_worker_failures_skips_retry():
    maisa = AsyncMock(spec=MaisaClient)
    maisa.get_updated_workers.return_value = []
    noxus = AsyncMock(spec=NoxusClient)
    noxus.get_updated_workers.return_value = []
    sync_failures = AsyncMock(spec=WorkerSyncFailureRepository)
    sync_failures.get_pending.return_value = []

    service = _service(maisa=maisa, noxus=noxus, sync_failures=sync_failures)
    summary = await service.run()

    assert summary == {"total": 0, "succeeded": 0, "failed": 0}


async def test_ingest_worker_creates_agent_and_notifies_when_use_case_missing():
    worker = _worker(use_case_id=None)
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.return_value = {"id": "new-agent"}
    notifier = AsyncMock(spec=AdminNotifier)
    monitoring = AsyncMock(spec=MonitoringStore)

    service = _service(auron=auron, notifier=notifier, monitoring=monitoring)
    ok = await service._ingest_worker(worker)

    assert ok is True
    auron.create_agent.assert_awaited_once_with(
        worker_id="W-1",
        use_case_id=settings.generic_use_case_id,
        tenant="maisa",
        name="Agente de prueba",
        description="Descripcion de prueba",
        use_case_owner=None,
        agent_owner="agent-owner@example.com",
        provider_version_id=None,
    )
    notifier.notify_pending_regularization.assert_awaited_once_with(
        workspace_id="WS-1", worker_id="W-1"
    )
    monitoring.record.assert_awaited_once()
    _, kwargs = monitoring.record.await_args
    assert kwargs["status"] == "success"
    assert kwargs["agent_id"] == "new-agent"
    assert kwargs["use_case_id"] == settings.generic_use_case_id


async def test_ingest_worker_records_error_status_and_does_not_raise_on_failure():
    worker = _worker()
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.side_effect = RuntimeError("boom")
    monitoring = AsyncMock(spec=MonitoringStore)

    service = _service(auron=auron, monitoring=monitoring)

    ok = await service._ingest_worker(worker)

    assert ok is False
    monitoring.record.assert_awaited_once()
    _, kwargs = monitoring.record.await_args
    assert kwargs["status"] == "error"
    assert kwargs["agent_id"] == ""


async def test_ingest_worker_isolates_monitoring_failure_too():
    # Un fallo al registrar en MonitoringStore (p.ej. si logging fallara)
    # tampoco debe romper el aislamiento del item.
    worker = _worker()
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.return_value = {"id": "new-agent"}
    monitoring = AsyncMock(spec=MonitoringStore)
    monitoring.record.side_effect = RuntimeError("logging blip")

    service = _service(auron=auron, monitoring=monitoring)

    ok = await service._ingest_worker(worker)

    assert ok is True


async def test_ingest_worker_marks_failure_resolved_on_success():
    worker = _worker()
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.return_value = {"id": "new-agent"}
    sync_failures = AsyncMock(spec=WorkerSyncFailureRepository)

    service = _service(auron=auron, sync_failures=sync_failures)
    ok = await service._ingest_worker(worker)

    assert ok is True
    sync_failures.mark_resolved.assert_awaited_once_with("W-1")
    sync_failures.record_failure.assert_not_awaited()


async def test_ingest_worker_records_failure_with_error_message():
    worker = _worker()
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.side_effect = RuntimeError("boom")
    sync_failures = AsyncMock(spec=WorkerSyncFailureRepository)

    service = _service(auron=auron, sync_failures=sync_failures)
    ok = await service._ingest_worker(worker)

    assert ok is False
    sync_failures.record_failure.assert_awaited_once_with(worker, "boom")
    sync_failures.mark_resolved.assert_not_awaited()


async def test_ingest_worker_isolates_sync_failures_tracking_error_too():
    # El propio tracking (record_failure/mark_resolved) es auxiliar - un
    # fallo ahi tampoco debe romper el aislamiento del item.
    worker = _worker()
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.return_value = {"id": "new-agent"}
    sync_failures = AsyncMock(spec=WorkerSyncFailureRepository)
    sync_failures.mark_resolved.side_effect = RuntimeError("db blip")

    service = _service(auron=auron, sync_failures=sync_failures)
    ok = await service._ingest_worker(worker)

    assert ok is True
