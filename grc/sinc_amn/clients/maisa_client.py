from motor.motor_asyncio import AsyncIOMotorClient

from sinc_amn.config import settings
from sinc_amn.models.worker import Worker


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

    async def get_updated_workers(self, day) -> list[Worker]:
        """Workers actualizados en Maisa para el dia D-1 dado.

        Confirmado: consulta directa a la BBDD de Maisa (AWS
        DocumentDB/MongoDB, via `self._mongo_client`,
        `settings.maisa_documentdb_dsn`).

        TODO: placeholder. Conexion confirmada (DSN real, dado por el
        equipo de Maisa/infra), pero falta confirmar: nombre de la base de
        datos dentro del cluster (el DSN no lo incluye), colección(es) de
        workers/agents y su esquema, campo de filtro para "actualizado en
        D-1", y cómo se relaciona cada worker con su caso de uso/label
        (mencionado como `worker_manager.labelIds` en ARCHITECTURE.md, sin
        confirmar si es el nombre real de la colección).
        """
        raise NotImplementedError
