import logging

from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.config import settings
from sinc_amn.repositories.noxus_use_case_label_repository import (
    NoxusUseCaseLabelRepository,
)

logger = logging.getLogger(__name__)


class NoxusLabelSyncService:
    """Orquesta "Funcionalidad * - Noxus": tabla intermedia -> Noxus.

    Mismo diseño que `MaisaLabelSyncService`. Toma los registros pendientes
    (status new/modified), los crea o actualiza en Noxus, y marca cada uno
    como 'synced' guardando el noxus_label_id devuelto. No escribe de
    vuelta en OpenPages (fuera de alcance actual, ver ARCHITECTURE.md).
    """

    def __init__(
        self, use_case_labels: NoxusUseCaseLabelRepository, noxus: NoxusClient
    ) -> None:
        self._use_case_labels = use_case_labels
        self._noxus = noxus

    async def run(self) -> dict:
        """Ejecuta "Funcionalidad * - Noxus" y devuelve un resumen
        `{total, succeeded, failed}`.

        Aislamiento por item (mismo criterio que Maisa): un label que falle
        (create/update/mark_synced) no interrumpe el resto del batch.
        """
        pending = await self._use_case_labels.get_pending_for_noxus(
            organization_id=settings.noxus_organization_id
        )

        succeeded = 0
        failed = 0
        for label in pending:
            try:
                if label.noxus_label_id is None:
                    noxus_label_id = await self._noxus.create_label(label)
                else:
                    await self._noxus.update_label(label.noxus_label_id, label)
                    noxus_label_id = label.noxus_label_id

                await self._use_case_labels.mark_synced(
                    label.id, noxus_label_id, expected_status=label.status
                )
            except Exception:
                failed += 1
                logger.exception(
                    "noxus_label_sync: fallo procesando label %s", label.id
                )
                continue
            succeeded += 1

        logger.info(
            "noxus_label_sync: procesados %d labels (%d ok, %d fallidos)",
            len(pending),
            succeeded,
            failed,
        )
        return {"total": len(pending), "succeeded": succeeded, "failed": failed}
