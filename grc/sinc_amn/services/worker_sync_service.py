import logging
from datetime import date, datetime, timedelta, timezone

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.config import settings
from sinc_amn.core.monitoring import MonitoringStore
from sinc_amn.core.notifications import AdminNotifier
from sinc_amn.models.worker import Worker

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
    ) -> None:
        self._auron = auron
        self._maisa = maisa
        self._noxus = noxus
        self._monitoring = monitoring
        self._notifier = notifier

    async def run(self) -> None:
        target_day = date.today() - timedelta(days=1)

        workers = [
            *await self._maisa.get_updated_workers(target_day),  # 1A
            *await self._noxus.get_updated_workers(target_day),  # 1B
        ]

        # 2AB: procesar la informacion combinada de ambos origenes.
        for worker in workers:
            await self._ingest_worker(worker)

        logger.info("worker_sync: procesados %d workers (D-1=%s)", len(workers), target_day)

    async def _ingest_worker(self, worker: Worker) -> None:
        # 3A/3B-5A/5B: alta/actualizacion del agente, con la tag worker_id y
        # el enlace al caso de uso incluidos en el mismo payload (confirmado:
        # no hay una llamada de asociacion aparte).
        agent = await self._auron.get_agent_by_worker_id(worker.worker_id)

        had_use_case = worker.use_case_id is not None
        use_case_id = worker.use_case_id or settings.generic_use_case_id

        status = "success"
        try:
            if agent is None:
                agent = await self._auron.create_agent(
                    worker_id=worker.worker_id,
                    workspace_id=worker.workspace_id,
                    use_case_id=use_case_id,
                )
            else:
                agent = await self._auron.update_agent(
                    agent_id=agent["id"],
                    workspace_id=worker.workspace_id,
                    use_case_id=use_case_id,
                )

            if not had_use_case:
                # 7A: ademas del fallback generico, se notifica al admin del
                # workspace para que lo regularice.
                await self._notifier.notify_pending_regularization(
                    workspace_id=worker.workspace_id, worker_id=worker.worker_id
                )
        except Exception:
            status = "error"
            raise
        finally:
            # 6AB: registrar el resultado de la ingesta para monitorizacion.
            await self._monitoring.record(
                worker_id=worker.worker_id,
                agent_id=agent["id"] if agent else "",
                use_case_id=use_case_id,
                status=status,
                timestamp=datetime.now(timezone.utc),
            )
