import logging
from datetime import date, datetime, timedelta, timezone

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.config import settings
from sinc_amn.core.business_entity import OTHER, business_entity_for
from sinc_amn.core.monitoring import MonitoringStore
from sinc_amn.core.notifications import AdminNotifier
from sinc_amn.models.worker import Worker
from sinc_amn.repositories.business_entity_repository import (
    BusinessEntityRepository,
)
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
        business_entities: BusinessEntityRepository,
    ) -> None:
        self._auron = auron
        self._maisa = maisa
        self._noxus = noxus
        self._monitoring = monitoring
        self._notifier = notifier
        self._use_case_labels = use_case_labels
        self._noxus_use_case_labels = noxus_use_case_labels
        self._sync_failures = sync_failures
        self._business_entities = business_entities
        # Casos de uso genericos ya buscados en este run, por (tenant, nombre).
        self._generic_use_cases: dict[tuple[str, str], str | None] = {}

    async def run(self, day: date | None = None) -> dict:
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
        # `day` solo para pruebas/reprocesos manuales; el CronJob no lo pasa.
        target_day = day or date.today() - timedelta(days=1)

        workers = await self._maisa.get_updated_workers(target_day)  # 1A
        if settings.noxus_workers_enabled:
            workers += await self._noxus.get_updated_workers(target_day)  # 1B

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
            "worker_sync: procesados %d workers (D-1=%s, %d ok, %d fallidos, "
            "%d reintentos)",
            len(workers),
            target_day,
            succeeded,
            failed,
            len(retried_workers),
        )
        return {"total": total, "succeeded": succeeded, "failed": failed}

    async def _resolve_use_case(self, worker: Worker) -> tuple[str, bool]:
        """Caso de uso del que cuelga el Agent: `(use_case_id, es_generico)`.

        Maisa: el del label `<ResourceID>_<nombre>` (ver
        MaisaClient.get_updated_workers) si existe en Auron. Si no hay label
        o el caso de uso no existe, el generico de la Business Entity del
        creador del agente: email -> datos de Workday -> BE
        (`business_entity_for`) -> caso de uso llamado
        `settings.auron_maisa_generic_use_case_name` en el Engagement de Maisa.
        Si ese caso de uso no existe es un fallo del worker (se reintenta en
        el siguiente run).

        Noxus: su `use_case_id` o `settings.generic_use_case_id`.
        """
        if worker.tenant != "maisa":
            if worker.use_case_id:
                return worker.use_case_id, False
            return settings.generic_use_case_id, True

        if worker.use_case_id and await self._auron.get_use_cases_by_resource_ids(
            [worker.use_case_id], worker.tenant
        ):
            return worker.use_case_id, False

        member = (
            await self._business_entities.get_member(worker.agent_owner)
            if worker.agent_owner
            else None
        )
        business_entity = business_entity_for(member)
        if business_entity == OTHER:
            business_entity = settings.auron_other_business_entity
        name = settings.auron_maisa_generic_use_case_name.format(
            business_entity=business_entity
        )
        key = (worker.tenant, name)
        if key not in self._generic_use_cases:
            self._generic_use_cases[key] = await self._auron.get_use_case_id_by_name(
                name, worker.tenant
            )
        use_case_id = self._generic_use_cases[key]
        if use_case_id is None:
            raise LookupError(
                f"no existe el caso de uso generico {name!r} en Auron "
                f"(tenant {worker.tenant})"
            )
        logger.info(
            "worker_sync: worker %s sin caso de uso valido (label: %s) -> "
            "generico %s de la BE %r",
            worker.worker_id,
            worker.use_case_id,
            use_case_id,
            business_entity,
        )
        return use_case_id, True

    async def _get_use_case_owner(
        self, worker: Worker, use_case_id: str
    ) -> str | None:
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
            # Backfill de workspace_id: Flujo 1 (OpenPages) no lo trae,
            # solo llega aqui via el propio Worker de Noxus. Auxiliar -
            # un fallo aqui no debe tumbar el aislamiento del item.
            if use_case_label and use_case_label.workspace_id is None:
                try:
                    await self._noxus_use_case_labels.set_workspace_id_if_missing(
                        use_case_id,
                        organization_id=settings.noxus_organization_id,
                        workspace_id=worker.workspace_id,
                    )
                except Exception:
                    logger.exception(
                        "worker_sync: fallo rellenando workspace_id de %s",
                        use_case_id,
                    )
        return use_case_label.owner if use_case_label else None

    async def _upsert_agent(
        self,
        worker: Worker,
        agent: dict | None,
        use_case_id: str,
        use_case_owner: str | None,
    ) -> dict:
        """Crea el Agent o lo actualiza (moviendolo de caso de uso si hace
        falta)."""
        if agent is None:
            return await self._auron.create_agent(
                worker_id=worker.worker_id,
                use_case_id=use_case_id,
                tenant=worker.tenant,
                name=worker.agent_name,
                description=worker.agent_description,
                use_case_owner=use_case_owner,
                agent_owner=worker.agent_owner,
                provider_version_id=worker.provider_version_id,
            )
        old_use_case_id = agent.get("primaryParentId")
        if old_use_case_id and old_use_case_id != use_case_id:
            # Confirmado (equipo Auron/IBM): el caso de uso
            # vinculado no se puede cambiar en un update_agent
            # (PUT) ni sobrescribiendo la asociacion - hay que
            # borrar la asociacion vieja y crear la nueva. No hace
            # falta borrar/recrear el Agent entero.
            await self._auron.dissociate(agent["id"], old_use_case_id)
            await self._auron.associate(
                agent["id"],
                use_case_id,
                association_definition_id="966",
                association_type="PARENT",
            )
        return await self._auron.update_agent(
            agent_id=agent["id"],
            tenant=worker.tenant,
            name=worker.agent_name,
            description=worker.agent_description,
            use_case_owner=use_case_owner,
            agent_owner=worker.agent_owner,
            provider_version_id=worker.provider_version_id,
        )

    async def _ingest_worker(self, worker: Worker) -> bool:
        """Ingesta un worker de forma aislada: nunca propaga un fallo, lo
        registra (log + intento de MonitoringStore) y devuelve False.
        """
        # 3A/3B-5A/5B: alta/actualizacion del agente, con la tag worker_id y
        # el enlace al caso de uso incluidos en el mismo payload de creacion
        # (confirmado: primaryParentId, sin llamada de asociacion aparte
        # para el alta). workspace_id no es un dato del Agent, asi que no se
        # le pasa aqui.
        # Si el Agent ya existe pero con otro caso de uso vinculado (p.ej.
        # estaba en el generico y ya tiene label), se mueve en _upsert_agent.
        agent: dict | None = None
        use_case_id = worker.use_case_id or ""

        status = "success"
        error_message = ""
        try:
            use_case_id, is_generic = await self._resolve_use_case(worker)
            agent = await self._auron.get_agent_by_worker_id(
                worker.worker_id, worker.tenant
            )

            use_case_owner = await self._get_use_case_owner(worker, use_case_id)
            agent = await self._upsert_agent(worker, agent, use_case_id, use_case_owner)

            if is_generic:
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
