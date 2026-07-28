from fastapi import APIRouter

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.core.monitoring import MonitoringStore
from sinc_amn.core.notifications import AdminNotifier
from sinc_amn.services.worker_sync_service import WorkerSyncService

router = APIRouter(prefix="/flows/workers", tags=["workers"])


@router.post("/sync", status_code=202)
async def sync_workers() -> dict:
    """Disparado por el CronJob diario. Ejecuta el Flujo 2 (workers D-1)."""
    service = WorkerSyncService(
        auron=AuronClient(),
        maisa=MaisaClient(),
        noxus=NoxusClient(),
        monitoring=MonitoringStore(),
        notifier=AdminNotifier(),
    )
    await service.run()
    return {"status": "accepted"}
