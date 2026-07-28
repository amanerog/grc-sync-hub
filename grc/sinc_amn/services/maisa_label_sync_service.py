import logging

from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.config import settings
from sinc_amn.repositories.use_case_label_repository import UseCaseLabelRepository

logger = logging.getLogger(__name__)


class MaisaLabelSyncService:
    """Orquesta "Funcionalidad *": tabla intermedia -> Maisa (DocumentDB).

    Toma los registros pendientes (status new/modified), los crea o
    actualiza en Maisa, y marca cada uno como 'synced' guardando el
    maisa_label_id devuelto. No escribe de vuelta en OpenPages (fuera de
    alcance actual, ver ARCHITECTURE.md).
    """

    def __init__(
        self, use_case_labels: UseCaseLabelRepository, maisa: MaisaClient
    ) -> None:
        self._use_case_labels = use_case_labels
        self._maisa = maisa

    async def run(self) -> None:
        pending = await self._use_case_labels.get_pending_for_maisa(
            organization_id=settings.maisa_organization_id
        )

        for label in pending:
            if label.maisa_label_id is None:
                maisa_label_id = await self._maisa.create_label(label)
            else:
                await self._maisa.update_label(label.maisa_label_id, label)
                maisa_label_id = label.maisa_label_id

            await self._use_case_labels.mark_synced(
                label.id, maisa_label_id, expected_status=label.status
            )

        logger.info("maisa_label_sync: procesados %d labels", len(pending))
