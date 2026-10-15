import httpx
from motor.motor_asyncio import AsyncIOMotorClient

from sinc_amn.config import settings
from sinc_amn.models.use_case_label import UseCaseLabel
from sinc_amn.models.worker import Worker


class MaisaClient:
    """Cliente contra Maisa - dos mecanismos de acceso distintos, no uno solo.

    - get_updated_workers: Flujo 2 (workers actualizados D-1). **Confirmado
      que NO es REST** - es una consulta directa a la BBDD de Maisa (AWS
      DocumentDB, compatible MongoDB, via `motor`/`self._mongo_client`).
    - create_label/update_label: "Funcionalidad *" (REST contra la Studio
      API de Maisa, via `self._client`/httpx, autenticado con un token del
      STS).

    Autenticacion REST en dos pasos, confirmada via ejemplo real (equipo
    Maisa): credenciales propias -> token del STS (pieza interna de
    Santander, `_get_access_token`) -> Bearer en cada llamada REST a Maisa.
    **Corrige un diseño anterior** (API key estatica fija como Bearer desde
    el constructor) - ese diseño anterior no reflejaba el mecanismo real.
    No aplica a `get_updated_workers` (acceso directo a BBDD, sin REST ni
    STS de por medio).

    create_label confirmado via ejemplo real (script bash del equipo de
    Maisa) en cuanto a URL/body/respuesta - ver su docstring; bloqueado en
    la practica hasta que se confirme la forma de la respuesta del STS
    (`_get_access_token`). update_label/get_updated_workers siguen sin
    confirmar del todo. Restricciones conocidas del lado Maisa (ver
    ARCHITECTURE.md): name 3-50 caracteres trimmed; unicidad de
    (organizationId, nameLower) por org, case-insensitive; workerCount no
    lo fija este cliente (lo mantiene Maisa via su propio $inc).
    """

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        mongo_client: AsyncIOMotorClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(base_url=settings.maisa_base_url)
        # AsyncIOMotorClient no abre conexion al construirse (lazy, mismo
        # criterio que httpx.AsyncClient) - confirmar la cadena de conexion
        # solo pasa al primer uso real.
        self._mongo_client = mongo_client or AsyncIOMotorClient(
            settings.maisa_documentdb_dsn
        )

    async def _get_access_token(self) -> str:
        """POST {maisa_sts_url} - intercambia las credenciales del STS por
        un token (Bearer) valido para llamar a Maisa.

        Confirmado via ejemplo real (equipo Maisa) la forma de la
        petición:
        - Headers: `X-Api-Key: {settings.maisa_sts_api_key}`,
          `Authorization: Basic <base64("{client_id}:{client_secret}")>`,
          `Content-Type: application/json`.
        - Body: `{"audience": [""], "claims": {"client_id":
          settings.maisa_sts_client_id}}` - confirmado explícitamente que
          `audience` vacío (`[""]`) es el valor correcto tal cual, no un
          placeholder sin rellenar.

        TODO: placeholder. Forma de la respuesta sin confirmar todavía
        (qué campo trae el token, si viene un `expires_in` o hay que leer
        el `exp` del propio JWT para cachear/renovar - mismo patrón que
        `AuronClient._get_access_token`, pero sin ejemplo real de
        respuesta aún para implementarlo con garantías).
        """
        raise NotImplementedError

    async def get_updated_workers(self, day) -> list[Worker]:
        """Workers actualizados en Maisa para el dia D-1 dado.

        **Confirmado: no es una llamada REST, es una consulta directa a la
        BBDD de Maisa** (AWS DocumentDB/MongoDB, via `self._mongo_client`,
        `settings.maisa_documentdb_dsn`) - no necesita el token del STS
        (eso solo aplica a create_label/update_label, la Studio API REST).

        TODO: placeholder. Conexion confirmada (DSN real, dado por el
        equipo de Maisa/infra), pero falta confirmar: nombre de la base de
        datos dentro del cluster (el DSN no lo incluye), colección(es) de
        workers/agents y su esquema, campo de filtro para "actualizado en
        D-1", y cómo se relaciona cada worker con su caso de uso/label
        (mencionado como `worker_manager.labelIds` en ARCHITECTURE.md, sin
        confirmar si es el nombre real de la colección).
        """
        raise NotImplementedError

    async def create_label(self, label: UseCaseLabel) -> str:
        """POST /organizations/{organization_id}/labels - crea el label en
        Maisa y devuelve el id generado alli (maisa_label_id).

        Confirmado via ejemplo real (script bash del equipo de Maisa,
        confirmado que /organizations/{org_id}/labels es la misma
        coleccion "labels" que UseCaseLabel, no otra funcionalidad
        distinta de Maisa):
        - `organization_id` va en la URL, no en el body ni como query param.
        - Auth Bearer con el token del STS (`_get_access_token`) -
          **corregido**: no es una API key estática fija, hay que pedir un
          token nuevo (el ejemplo no aclara si es reutilizable entre
          llamadas o hay que pedirlo cada vez - de momento se pide en cada
          llamada, sin cachear, hasta confirmar si el STS admite reuso).
        - Body minimo confirmado: solo `{"name": ...}` - el ejemplo no
          incluye `entity`/`owner`/`nameLower`/`organizationId` en el body
          (Maisa calcula `nameLower` en su lado, ver restricciones en el
          docstring de la clase). Sin confirmar si admite mas campos
          aparte de `name` en la creacion real de casos de uso (el ejemplo
          solo crea labels de prueba tipo entorno/departamento).
        - La respuesta trae al menos `id`/`name` (confirmado via el `jq`
          del ejemplo) - `id` es el `maisa_label_id` a persistir.

        Bloqueado en la práctica hasta confirmar la respuesta del STS (ver
        `_get_access_token`) - la llamada a Maisa en sí ya está lista.
        """
        token = await self._get_access_token()
        response = await self._client.post(
            f"/organizations/{label.organization_id}/labels",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": label.name},
        )
        response.raise_for_status()
        return response.json()["id"]

    async def update_label(self, maisa_label_id: str, label: UseCaseLabel) -> None:
        """Actualiza un label existente en Maisa (identificado por maisa_label_id).

        TODO: placeholder. El ejemplo real visto solo cubre creacion (ver
        `create_label`) - sin confirmar metodo HTTP/URL de actualizacion.
        Hipotesis mas probable por convencion REST (sin confirmar):
        `PUT`/`PATCH /organizations/{organization_id}/labels/{maisa_label_id}`.
        Necesitaria el mismo token del STS que create_label.
        """
        raise NotImplementedError
