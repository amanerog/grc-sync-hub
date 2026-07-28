from fastapi import APIRouter

from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.db.pool import get_pool
from sinc_amn.repositories.use_case_label_repository import UseCaseLabelRepository
from sinc_amn.services.maisa_label_sync_service import MaisaLabelSyncService

router = APIRouter(prefix="/flows/maisa-labels", tags=["maisa-labels"])


@router.post("/sync", status_code=202)
async def sync_maisa_labels() -> dict:
    """Disparado por el CronJob horario. Ejecuta "Funcionalidad *"."""
    service = MaisaLabelSyncService(
        use_case_labels=UseCaseLabelRepository(get_pool()),
        maisa=MaisaClient(),
    )
    await service.run()
    return {"status": "accepted"}
