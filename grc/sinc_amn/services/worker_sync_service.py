import logging
from datetime import date, datetime, timedelta, timezone

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.config import settings
from sinc_amn.core.monitoring import MonitoringStore
from sinc_amn.core.notifications import AdminNotifier
from sinc_amn.models.worker import Worker
from sinc_amn.repositories.noxus_use_case_label_repository import (
    NoxusUseCaseLabelRepository,
)
from sinc_amn.repositories.use_case_label_repository import UseCaseLabelRepository
from sinc_amn.repositories.worker_sync_failure_repository import (
    WorkerSyncFailureRepository,
)

logger = logging.getLogger(__name__)


class WorkerSyncService:
    """Orquesta el Flujo 2: Maisa/Noxus -> Auron (workers de D-1).

    Confirmado: ambos origenes contribuyen (1A Maisa, 1B Noxus) con el mismo
    modelo logico (Worker), sin necesidad de deduplicar entre ellos.
    """

    def __init__(
        self,
        auron: AuronClient,
        maisa: MaisaClient,
        noxus: NoxusClient,
        monitoring: MonitoringStore,
        notifier: AdminNotifier,
        use_case_labels: UseCaseLabelRepository,
        noxus_use_case_labels: NoxusUseCaseLabelRepository,
        sync_failures: WorkerSyncFailureRepository,
    ) -> None:
        self._auron = auron
        self._maisa = maisa
        self._noxus = noxus
        self._monitoring = monitoring
        self._notifier = notifier
        self._use_case_labels = use_case_labels
        self._noxus_use_case_labels = noxus_use_case_labels
        self._sync_failures = sync_failures

    async def run(self) -> dict:
        """Ejecuta el Flujo 2 y devuelve un resumen `{total, succeeded, failed}`.

        Aislamiento por item (confirmado): un worker que falle no interrumpe
        el resto del batch, sea cual sea su origen (Maisa/Noxus).

        Ademas del batch normal (D-1), se reintentan los workers que
        fallaron en runs anteriores (`WorkerSyncFailureRepository`),
        reconstruidos desde su ultima foto guardada - cierra el mismo
        hueco de ventana rodante que ya resolvimos para Flujo 1, adaptado
        a que Maisa/Noxus no ofrecen un lookup por ID (ver docstring de
        `WorkerSyncFailureRepository`).
        """
        target_day = date.today() - timedelta(days=1)

        workers = [
            *await self._maisa.get_updated_workers(target_day),  # 1A
            *await self._noxus.get_updated_workers(target_day),  # 1B
        ]

        # 2AB: procesar la informacion combinada de ambos origenes.
        results = [await self._ingest_worker(worker) for worker in workers]

        retried_workers = await self._sync_failures.get_pending()
        results.extend(
            [await self._ingest_worker(worker) for worker in retried_workers]
        )

        total = len(results)
        succeeded = sum(results)
        failed = total - succeeded
        logger.info(
            "worker_sync: procesados %d workers (D-1=%s, %d ok, %d fallidos, %d reintentos)",
            len(workers),
            target_day,
            succeeded,
            failed,
            len(retried_workers),
        )
        return {"total": total, "succeeded": succeeded, "failed": failed}

    async def _ingest_worker(self, worker: Worker) -> bool:
        """Ingesta un worker de forma aislada: nunca propaga un fallo, lo
        registra (log + intento de MonitoringStore) y devuelve False.
        """
        # 3A/3B-5A/5B: alta/actualizacion del agente, con la tag worker_id y
        # el enlace al caso de uso incluidos en el mismo payload (confirmado:
        # no hay una llamada de asociacion aparte). workspace_id no es un
        # dato del Agent (vive en el propio caso de uso, solo Noxus - Maisa
        # no tiene workspace_id asociado), asi que no se le pasa aqui.
        agent: dict | None = None
        had_use_case = worker.use_case_id is not None
        use_case_id = worker.use_case_id or settings.generic_use_case_id

        status = "success"
        error_message = ""
        try:
            agent = await self._auron.get_agent_by_worker_id(worker.worker_id)

            # Owner del Use Case (field "3261" del Agent, distinto del owner
            # del propio Agent) - se lee de la tabla intermedia del tenant
            # correspondiente (poblada por Flujo 1), sin GET adicional a
            # OpenPages.
            if worker.tenant == "maisa":
                use_case_label = await self._use_case_labels.get_by_resource_id(
                    use_case_id, organization_id=settings.maisa_organization_id
                )
            else:
                use_case_label = await self._noxus_use_case_labels.get_by_resource_id(
                    use_case_id, organization_id=settings.noxus_organization_id
                )
            use_case_owner = use_case_label.owner if use_case_label else None

            if agent is None:
                agent = await self._auron.create_agent(
                    worker_id=worker.worker_id,
                    use_case_id=use_case_id,
                    tenant=worker.tenant,
                    name=worker.agent_name,
                    description=worker.agent_description,
                    use_case_owner=use_case_owner,
                    agent_owner=worker.agent_owner,
                )
            else:
                agent = await self._auron.update_agent(
                    agent_id=agent["id"],
                    use_case_id=use_case_id,
                    tenant=worker.tenant,
                    name=worker.agent_name,
                    description=worker.agent_description,
                    use_case_owner=use_case_owner,
                    agent_owner=worker.agent_owner,
                )

            if not had_use_case:
                # 7A: ademas del fallback generico, se notifica al admin del
                # workspace para que lo regularice.
                await self._notifier.notify_pending_regularization(
                    workspace_id=worker.workspace_id, worker_id=worker.worker_id
                )
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            logger.exception(
                "worker_sync: fallo ingiriendo worker %s", worker.worker_id
            )
        finally:
            # 6AB: registrar el resultado de la ingesta para monitorizacion
            # (MonitoringStore, log estructurado -> CloudWatch). Un fallo
            # aqui es en si mismo un fallo aislado: no debe tumbar el
            # aislamiento del resto del batch, solo se loguea.
            try:
                await self._monitoring.record(
                    worker_id=worker.worker_id,
                    agent_id=agent["id"] if agent else "",
                    use_case_id=use_case_id,
                    status=status,
                    timestamp=datetime.now(timezone.utc),
                )
            except Exception:
                logger.exception(
                    "worker_sync: fallo registrando monitorizacion de %s",
                    worker.worker_id,
                )

        await self._track_result(
            worker, succeeded=(status == "success"), error=error_message
        )

        return status == "success"

    async def _track_result(
        self, worker: Worker, succeeded: bool, error: str = ""
    ) -> None:
        # El propio tracking de fallos es auxiliar (mismo criterio que
        # Flujo 1): un fallo aqui no debe tumbar el aislamiento del resto
        # del batch, solo se loguea.
        try:
            if succeeded:
                await self._sync_failures.mark_resolved(worker.worker_id)
            else:
                await self._sync_failures.record_failure(worker, error)
        except Exception:
            logger.exception(
                "worker_sync: fallo actualizando tracking de %s", worker.worker_id
            )
