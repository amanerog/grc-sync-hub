from fastapi import APIRouter, Response

from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.db.pool import get_pool
from sinc_amn.repositories.use_case_label_repository import UseCaseLabelRepository
from sinc_amn.services.maisa_label_sync_service import MaisaLabelSyncService

router = APIRouter(prefix="/flows/maisa-labels", tags=["maisa-labels"])


@router.post("/sync")
async def sync_maisa_labels(response: Response) -> dict:
    """Disparado por el CronJob horario. Ejecuta "Funcionalidad *".

    202 si todos los items del batch se procesaron bien (o no habia
    ninguno); 207 (Multi-Status) si hubo algun fallo aislado.
    """
    service = MaisaLabelSyncService(
        use_case_labels=UseCaseLabelRepository(get_pool()),
        maisa=MaisaClient(),
    )
    summary = await service.run()
    response.status_code = 202 if summary["failed"] == 0 else 207
    return {"status": "accepted", **summary}
