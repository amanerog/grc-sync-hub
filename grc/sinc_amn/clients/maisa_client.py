import logging
import re
from datetime import date, datetime, time, timedelta

from motor.motor_asyncio import AsyncIOMotorClient

from sinc_amn.config import settings
from sinc_amn.models.worker import Worker

logger = logging.getLogger(__name__)


class MaisaClient:
    """Cliente contra la BBDD de Maisa (AWS DocumentDB, compatible MongoDB).

    - get_updated_workers: Flujo 2 (workers actualizados D-1). Confirmado
      que es una consulta directa a la BBDD, no REST.

    **Confirmado explícitamente: el envío de labels hacia Maisa
    ("Funcionalidad \\*") no lo hace este microservicio** - lo regulariza
    a mano el propio equipo de Maisa. Por eso este cliente ya no tiene
    `create_label`/`update_label` ni la autenticación REST vía STS que
    tenían antes (`MaisaLabelSyncService`, el endpoint
    `POST /flows/maisa-labels/sync` y esos métodos se han eliminado del
    todo - recuperables del historial de git si se retoma la
    automatización más adelante). La tabla intermedia (Flujo 1,
    `UseCaseLabelRepository`) se sigue poblando igual, solo para dejar
    constancia - nadie la consume automáticamente hacia Maisa.
    """

    def __init__(self, mongo_client: AsyncIOMotorClient | None = None) -> None:
        # AsyncIOMotorClient no abre conexion al construirse (lazy) -
        # confirmar la cadena de conexion solo pasa al primer uso real.
        self._mongo_client = mongo_client or AsyncIOMotorClient(
            settings.maisa_documentdb_dsn
        )

    @property
    def _db(self):
        return self._mongo_client[settings.maisa_documentdb_database]

    async def check_connection(self) -> dict:
        """Diagnostico de conectividad: ping al cluster + colecciones de la BBDD.

        Fuerza la conexion real (red, TLS y autenticacion), que el
        constructor no abre. Propaga las excepciones de pymongo tal cual.
        """
        await self._mongo_client.admin.command("ping")
        collections = await self._db.list_collection_names()
        return {
            "database": settings.maisa_documentdb_database,
            "collections": sorted(collections),
        }

    async def get_updated_workers(self, day: date) -> list[Worker]:
        """Agentes de Maisa con algun cambio en el dia `day` (D-1).

        Modelo confirmado contra el dump real de `gpp_maisa_metrics`:
        - `worker_manager` es el agente (nombre real, workspace, labels);
          cada documento de `worker` es una VERSION suya (`worker_version`
          1..N, `worker_name` tipo "New Version v3"). Un Agent de OpenPages
          = un `worker_manager` (`Worker.worker_id` = su id).
        - "Actualizado en D-1" = alguna version con `maisa_updated_ts` ese
          dia. No `updated_ts`: ese lo toca el proceso PROFILER aunque el
          worker no cambie (`update_user` siempre "PROFILER").
        - Solo agentes con una version DEPLOYED (la mas alta es la que se
          envia como `provider_version_id`), no borrados ni excluidos
          (`is_user_excluded`), de `settings.maisa_workers_entity`/
          `maisa_workers_environment` (la BBDD mezcla entidades/entornos).
        - Caso de uso: `worker_manager.label_ids` -> `label.name`, con
          formato acordado `<ResourceID>_<nombre>` - el prefijo numerico es
          el Resource ID del caso de uso en OpenPages. Sin label con ese
          formato -> `use_case_id=None` (WorkerSyncService no lo crea).
        - Owner del Agent: `email` del `user` cuyo `user_id` es
          `worker_manager.worker_manager_user`.
        """
        start = datetime.combine(day, time.min)
        end = start + timedelta(days=1)
        scope = {
            "entity": settings.maisa_workers_entity,
            "environment": settings.maisa_workers_environment,
        }

        manager_ids = await self._db.worker.distinct(
            "worker_manager",
            {**scope, "maisa_updated_ts": {"$gte": start, "$lt": end}},
        )
        if not manager_ids:
            return []

        managers = await self._db.worker_manager.find(
            {
                **scope,
                "worker_manager": {"$in": manager_ids},
                "is_deleted": False,
                "is_user_excluded": {"$ne": True},
            }
        ).to_list(None)

        deployed: dict[str, dict] = {}
        async for version in self._db.worker.find(
            {
                "worker_manager": {"$in": [m["worker_manager"] for m in managers]},
                "worker_status": "DEPLOYED",
                "is_deleted": False,
            }
        ):
            current = deployed.get(version["worker_manager"])
            if current is None or version["worker_version"] > current["worker_version"]:
                deployed[version["worker_manager"]] = version

        label_ids = {lid for m in managers for lid in m.get("label_ids") or []}
        label_names = {
            label["label_id"]: label["name"]
            async for label in self._db.label.find(
                {"label_id": {"$in": list(label_ids)}, "is_deleted": False}
            )
        }
        user_ids = {m.get("worker_manager_user") for m in managers} - {None}
        emails = {
            user["user_id"]: user.get("email")
            async for user in self._db.user.find({"user_id": {"$in": list(user_ids)}})
        }

        workers = []
        for manager in managers:
            version = deployed.get(manager["worker_manager"])
            if version is None:
                continue
            workers.append(
                Worker(
                    worker_id=manager["worker_manager"],
                    workspace_id=manager["workspace"],
                    tenant="maisa",
                    use_case_id=_use_case_id_from_labels(
                        manager["worker_manager"],
                        [label_names.get(lid) for lid in manager.get("label_ids") or []],
                    ),
                    updated_at=day,
                    agent_name=manager.get("worker_manager_name"),
                    agent_owner=emails.get(manager.get("worker_manager_user")),
                    provider_version_id=str(version["worker_version"]),
                )
            )
        return workers


# Formato acordado para los labels de Maisa que representan un caso de uso
# de OpenPages: "<ResourceID>_<nombre>" (p.ej. "559_Riesgos-AdmisionIndividuos").
_USE_CASE_LABEL_RE = re.compile(r"^(\d+)_")


def _use_case_id_from_labels(manager_id: str, names: list[str | None]) -> str | None:
    """Resource ID del caso de uso a partir de los labels del agente, o None.

    Si varios labels tienen Resource ID distinto se usa el primero (orden de
    `label_ids`) y se deja aviso en el log.
    """
    ids = []
    for name in names:
        match = _USE_CASE_LABEL_RE.match(name or "")
        if match and match.group(1) not in ids:
            ids.append(match.group(1))
    if len(ids) > 1:
        logger.warning(
            "maisa: worker_manager %s con varios casos de uso en sus labels %s, se usa %s",
            manager_id,
            ids,
            ids[0],
        )
    return ids[0] if ids else None
