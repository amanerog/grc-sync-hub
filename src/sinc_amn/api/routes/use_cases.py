from fastapi import APIRouter

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.core.checkpoint import CheckpointStore
from sinc_amn.db.pool import get_pool
from sinc_amn.repositories.use_case_label_repository import UseCaseLabelRepository
from sinc_amn.services.use_case_sync_service import UseCaseSyncService

router = APIRouter(prefix="/flows/use-cases", tags=["use-cases"])


@router.post("/sync", status_code=202)
async def sync_use_cases() -> dict:
    """Disparado por el CronJob horario. Ejecuta el Flujo 1."""
    service = UseCaseSyncService(
        auron=AuronClient(),
        use_case_labels=UseCaseLabelRepository(get_pool()),
        noxus=NoxusClient(),
        checkpoints=CheckpointStore(),
    )
    await service.run()
    return {"status": "accepted"}
