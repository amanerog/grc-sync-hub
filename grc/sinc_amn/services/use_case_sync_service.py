import logging

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.config import settings
from sinc_amn.repositories.use_case_label_repository import UseCaseLabelRepository

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
    ) -> None:
        self._auron = auron
        self._use_case_labels = use_case_labels
        self._noxus = noxus

    async def run(self) -> None:
        use_cases = await self._auron.get_use_cases(tenants=TENANTS)

        # TODO: definir estrategia de fallo parcial (ver ARCHITECTURE.md):
        # si un destino falla para un caso de uso concreto, hoy el error
        # simplemente interrumpe el resto del batch.
        for use_case in use_cases:
            if use_case.tenant == "maisa":
                await self._use_case_labels.upsert_from_use_case(
                    use_case, organization_id=settings.maisa_organization_id
                )
            elif use_case.tenant == "noxus":
                await self._noxus.push_use_case(use_case)

        logger.info("use_case_sync: procesados %d casos de uso", len(use_cases))
