from fastapi import APIRouter, Response

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.core.monitoring import MonitoringStore
from sinc_amn.core.notifications import AdminNotifier
from sinc_amn.services.worker_sync_service import WorkerSyncService

router = APIRouter(prefix="/flows/workers", tags=["workers"])


@router.post("/sync")
async def sync_workers(response: Response) -> dict:
    """Disparado por el CronJob diario. Ejecuta el Flujo 2 (workers D-1).

    202 si todos los items del batch se procesaron bien (o no habia
    ninguno); 207 (Multi-Status) si hubo algun fallo aislado.
    """
    service = WorkerSyncService(
        auron=AuronClient(),
        maisa=MaisaClient(),
        noxus=NoxusClient(),
        monitoring=MonitoringStore(),
        notifier=AdminNotifier(),
    )
    summary = await service.run()
    response.status_code = 202 if summary["failed"] == 0 else 207
    return {"status": "accepted", **summary}
