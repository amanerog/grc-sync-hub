import httpx

from sinc_amn.config import settings
from sinc_amn.models.use_case_label import UseCaseLabel
from sinc_amn.models.worker import Worker


class MaisaClient:
    """Cliente HTTP contra la API de Maisa.

    - get_updated_workers: Flujo 2 (workers actualizados D-1).
    - create_label/update_label: "Funcionalidad *" (push de la tabla
      intermedia a la coleccion "labels" de la DocumentDB de Maisa).

    create_label confirmado via ejemplo real (script bash del equipo de
    Maisa) - ver su docstring. update_label/get_updated_workers siguen sin
    confirmar. Restricciones conocidas del lado Maisa (ver ARCHITECTURE.md):
    name 3-50 caracteres trimmed; unicidad de (organizationId, nameLower)
    por org, case-insensitive; workerCount no lo fija este cliente (lo
    mantiene Maisa via su propio $inc).
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=settings.maisa_base_url,
            headers={"Authorization": f"Bearer {settings.maisa_api_key}"},
        )

    async def get_updated_workers(self, day) -> list[Worker]:
        """Workers actualizados en Maisa para el dia D-1 dado."""
        raise NotImplementedError

    async def create_label(self, label: UseCaseLabel) -> str:
        """POST /organizations/{organization_id}/labels - crea el label en
        Maisa y devuelve el id generado alli (maisa_label_id).

        Confirmado via ejemplo real (script bash del equipo de Maisa,
        confirmado que /organizations/{org_id}/labels es la misma
        coleccion "labels" que UseCaseLabel, no otra funcionalidad
        distinta de Maisa):
        - `organization_id` va en la URL, no en el body ni como query param.
        - Auth Bearer - coincide con lo que ya hace este cliente
          (`Authorization: Bearer {settings.maisa_api_key}`, fijo desde el
          constructor), asumiendo que el token del ejemplo es la propia
          API key usada tal cual (el ejemplo no muestra ningun intercambio
          previo tipo IAM de Auron).
        - Body minimo confirmado: solo `{"name": ...}` - el ejemplo no
          incluye `entity`/`owner`/`nameLower`/`organizationId` en el body
          (Maisa calcula `nameLower` en su lado, ver restricciones en el
          docstring de la clase). Sin confirmar si admite mas campos
          aparte de `name` en la creacion real de casos de uso (el ejemplo
          solo crea labels de prueba tipo entorno/departamento).
        - La respuesta trae al menos `id`/`name` (confirmado via el `jq`
          del ejemplo) - `id` es el `maisa_label_id` a persistir.
        """
        response = await self._client.post(
            f"/organizations/{label.organization_id}/labels",
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
        """
        raise NotImplementedError
