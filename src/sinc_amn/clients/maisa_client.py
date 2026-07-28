import httpx

from sinc_amn.config import settings
from sinc_amn.models.use_case_label import UseCaseLabel
from sinc_amn.models.worker import Worker


class MaisaClient:
    """Cliente HTTP contra la API de Maisa.

    - get_updated_workers: Flujo 2 (workers actualizados D-1).
    - create_label/update_label: "Funcionalidad *" (push de la tabla
      intermedia a la coleccion "labels" de la DocumentDB de Maisa).

    Contrato REST aun no confirmado con el equipo de Maisa (auth, URL,
    payload exacto) - placeholders con TODO, igual que la consulta masiva de
    OpenPages en AuronClient. Restricciones conocidas del lado Maisa (ver
    ARCHITECTURE.md): name 3-50 caracteres trimmed; unicidad de
    (organizationId, nameLower) por org, case-insensitive; workerCount no lo
    fija este cliente (lo mantiene Maisa via su propio $inc).
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
        """Crea el label en Maisa y devuelve el id generado alli (maisa_label_id)."""
        raise NotImplementedError

    async def update_label(self, maisa_label_id: str, label: UseCaseLabel) -> None:
        """Actualiza un label existente en Maisa (identificado por maisa_label_id)."""
        raise NotImplementedError
