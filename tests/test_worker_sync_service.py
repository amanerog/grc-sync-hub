from datetime import date

from unittest.mock import AsyncMock

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.config import settings
from sinc_amn.core.monitoring import MonitoringStore
from sinc_amn.core.notifications import AdminNotifier
from sinc_amn.models.worker import Worker
from sinc_amn.services.worker_sync_service import WorkerSyncService


def _worker(**overrides) -> Worker:
    data = dict(
        worker_id="W-1",
        workspace_id="WS-1",
        use_case_id="UC-1",
        updated_at=date(2026, 7, 27),
    )
    data.update(overrides)
    return Worker(**data)


def _service(auron=None, maisa=None, noxus=None, monitoring=None, notifier=None):
    return WorkerSyncService(
        auron=auron or AsyncMock(spec=AuronClient),
        maisa=maisa or AsyncMock(spec=MaisaClient),
        noxus=noxus or AsyncMock(spec=NoxusClient),
        monitoring=monitoring or AsyncMock(spec=MonitoringStore),
        notifier=notifier or AsyncMock(spec=AdminNotifier),
    )


async def test_run_combines_maisa_and_noxus_workers_and_updates_existing_agent():
    worker = _worker()
    maisa = AsyncMock(spec=MaisaClient)
    maisa.get_updated_workers.return_value = [worker]
    noxus = AsyncMock(spec=NoxusClient)
    noxus.get_updated_workers.return_value = []
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = {"id": "agent-1"}
    monitoring = AsyncMock(spec=MonitoringStore)

    service = _service(auron=auron, maisa=maisa, noxus=noxus, monitoring=monitoring)
    summary = await service.run()

    auron.update_agent.assert_awaited_once_with(
        agent_id="agent-1", use_case_id="UC-1"
    )
    auron.create_agent.assert_not_awaited()
    monitoring.record.assert_awaited_once()
    assert summary == {"total": 1, "succeeded": 1, "failed": 0}


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
    auron.create_agent.assert_awaited_once_with(worker_id="W-2", use_case_id="UC-1")
    assert summary == {"total": 2, "succeeded": 1, "failed": 1}


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
        worker_id="W-1", use_case_id=settings.generic_use_case_id
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
    # MonitoringStore.record sigue en placeholder (NotImplementedError) por
    # defecto - un fallo ahi tampoco debe romper el aislamiento del item.
    worker = _worker()
    auron = AsyncMock(spec=AuronClient)
    auron.get_agent_by_worker_id.return_value = None
    auron.create_agent.return_value = {"id": "new-agent"}
    monitoring = AsyncMock(spec=MonitoringStore)
    monitoring.record.side_effect = NotImplementedError

    service = _service(auron=auron, monitoring=monitoring)

    ok = await service._ingest_worker(worker)

    assert ok is True
