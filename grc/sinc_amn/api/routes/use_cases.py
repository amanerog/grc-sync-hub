from fastapi import APIRouter, Response

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.db.pool import get_pool
from sinc_amn.repositories.noxus_use_case_label_repository import (
    NoxusUseCaseLabelRepository,
)
from sinc_amn.repositories.use_case_label_repository import UseCaseLabelRepository
from sinc_amn.repositories.use_case_sync_failure_repository import (
    UseCaseSyncFailureRepository,
)
from sinc_amn.services.use_case_sync_service import UseCaseSyncService

router = APIRouter(prefix="/flows/use-cases", tags=["use-cases"])


@router.post("/sync")
async def sync_use_cases(response: Response) -> dict:
    """Disparado por el CronJob horario. Ejecuta el Flujo 1.

    202 si todos los items del batch se procesaron bien (o no habia
    ninguno); 207 (Multi-Status) si hubo algun fallo aislado, para que el
    CronJob/alerting lo pueda distinguir de un run limpio.
    """
    service = UseCaseSyncService(
        auron=AuronClient(),
        use_case_labels=UseCaseLabelRepository(get_pool()),
        noxus_use_case_labels=NoxusUseCaseLabelRepository(get_pool()),
        sync_failures=UseCaseSyncFailureRepository(get_pool()),
    )
    summary = await service.run()
    response.status_code = 202 if summary["failed"] == 0 else 207
    return {"status": "accepted", **summary}
