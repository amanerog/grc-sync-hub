from fastapi import APIRouter, Response

from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.db.pool import get_pool
from sinc_amn.repositories.noxus_use_case_label_repository import (
    NoxusUseCaseLabelRepository,
)
from sinc_amn.services.noxus_label_sync_service import NoxusLabelSyncService

router = APIRouter(prefix="/flows/noxus-labels", tags=["noxus-labels"])


@router.post("/sync")
async def sync_noxus_labels(response: Response) -> dict:
    """Disparado por el CronJob horario. Ejecuta "Funcionalidad * - Noxus".

    202 si todos los items del batch se procesaron bien (o no habia
    ninguno); 207 (Multi-Status) si hubo algun fallo aislado.
    """
    service = NoxusLabelSyncService(
        use_case_labels=NoxusUseCaseLabelRepository(get_pool()),
        noxus=NoxusClient(),
    )
    summary = await service.run()
    response.status_code = 202 if summary["failed"] == 0 else 207
    return {"status": "accepted", **summary}
