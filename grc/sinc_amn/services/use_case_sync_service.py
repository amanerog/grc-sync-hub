import logging

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.config import settings
from sinc_amn.models.use_case import UseCase
from sinc_amn.repositories.use_case_label_repository import UseCaseLabelRepository
from sinc_amn.repositories.use_case_sync_failure_repository import (
    UseCaseSyncFailureRepository,
)

logger = logging.getLogger(__name__)

TENANTS = ["maisa", "noxus"]


class UseCaseSyncService:
    """Orquesta el Flujo 1: Auron/OpenPages -> Maisa/Noxus.

    Destino Maisa ("Funcionalidad 1"): persiste en la tabla intermedia via
    UseCaseLabelRepository. El envio real a la instalacion de Maisa
    (eDOCUMENT db) lo hace otro componente ("Funcionalidad *"), fuera de
    alcance de este servicio.

    Destino Noxus: push automatico (Noxus asocia el caso de uso el solo),
    pendiente de implementar el contrato real (ver ARCHITECTURE.md).

    La ventana de fechas la resuelve `AuronClient` en el propio WHERE de la
    consulta (`settings.auron_use_cases_since`), no un checkpoint persistido.
    """

    def __init__(
        self,
        auron: AuronClient,
        use_case_labels: UseCaseLabelRepository,
        noxus: NoxusClient,
        sync_failures: UseCaseSyncFailureRepository,
    ) -> None:
        self._auron = auron
        self._use_case_labels = use_case_labels
        self._noxus = noxus
        self._sync_failures = sync_failures

    async def run(self) -> dict:
        """Ejecuta el Flujo 1 y devuelve un resumen `{total, succeeded, failed}`.

        Aislamiento por item (confirmado): un caso de uso que falle no
        interrumpe el resto del batch, ni de su mismo tenant ni del otro -
        Maisa y Noxus ya quedan independientes por construccion, al
        despacharse a destinos distintos dentro de la misma iteracion.

        Ademas del batch normal (filtrado por `settings.auron_use_cases_since`),
        se reintentan por Resource ID explicito los items que fallaron en
        runs anteriores (`UseCaseSyncFailureRepository`) - esto cierra el
        hueco de que un item deje de caer dentro de la ventana de fecha
        antes de arreglarse (p.ej. al cruzar medianoche).
        """
        use_cases = await self._auron.get_use_cases(tenants=TENANTS)
        results = [await self._sync_one(use_case) for use_case in use_cases]

        retried = await self._retry_pending_failures()
        results.extend(retried)

        total = len(results)
        succeeded = sum(results)
        failed = total - succeeded
        logger.info(
            "use_case_sync: procesados %d casos de uso (%d ok, %d fallidos, %d reintentos)",
            total,
            succeeded,
            failed,
            len(retried),
        )
        return {"total": total, "succeeded": succeeded, "failed": failed}

    async def _retry_pending_failures(self) -> list[bool]:
        pending = await self._sync_failures.get_pending()
        if not pending:
            return []

        by_tenant: dict[str, list[str]] = {}
        for item in pending:
            by_tenant.setdefault(item["tenant"], []).append(item["resource_id"])

        results = []
        for tenant, resource_ids in by_tenant.items():
            use_cases = await self._auron.get_use_cases_by_resource_ids(
                resource_ids, tenant
            )
            results.extend([await self._sync_one(use_case) for use_case in use_cases])
        return results

    async def _sync_one(self, use_case: UseCase) -> bool:
        """Procesa un caso de uso y actualiza su tracking de fallos.
        Nunca propaga - devuelve si tuvo exito."""
        try:
            if use_case.tenant == "maisa":
                await self._use_case_labels.upsert_from_use_case(
                    use_case, organization_id=settings.maisa_organization_id
                )
            elif use_case.tenant == "noxus":
                await self._noxus.push_use_case(use_case)
        except Exception as exc:
            logger.exception(
                "use_case_sync: fallo procesando caso de uso %s (tenant=%s)",
                use_case.resource_id,
                use_case.tenant,
            )
            await self._track_result(use_case, succeeded=False, error=str(exc))
            return False

        await self._track_result(use_case, succeeded=True)
        return True

    async def _track_result(
        self, use_case: UseCase, succeeded: bool, error: str = ""
    ) -> None:
        # El propio tracking de fallos es auxiliar: un fallo aqui (p.ej. un
        # blip de la BBDD) no debe tumbar el aislamiento del resto del
        # batch, solo se loguea.
        try:
            if succeeded:
                await self._sync_failures.mark_resolved(use_case.resource_id)
            else:
                await self._sync_failures.record_failure(
                    use_case.resource_id, use_case.tenant, error
                )
        except Exception:
            logger.exception(
                "use_case_sync: fallo actualizando tracking de %s",
                use_case.resource_id,
            )
