import httpx

from sinc_amn.config import settings
from sinc_amn.models.noxus_use_case_label import NoxusUseCaseLabel
from sinc_amn.models.worker import Worker


class NoxusClient:
    """Cliente HTTP contra la API de Noxus.

    Corregido respecto a un diseño anterior: Noxus SI usa tabla intermedia
    ("Funcionalidad 1 - Noxus" / "Funcionalidad * - Noxus"), confirmado -
    mismo patron que Maisa (`NoxusUseCaseLabelRepository`), ya no push
    directo por item. Contrato REST aun no confirmado con el equipo de
    Noxus (auth, URL, payload exacto) - placeholders con TODO, igual que
    Maisa antes de tener ejemplos reales.
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=settings.noxus_base_url,
            headers={"Authorization": f"Bearer {settings.noxus_api_key}"},
        )

    async def get_updated_workers(self, day) -> list[Worker]:
        """Workers actualizados en Noxus para el dia D-1 dado."""
        raise NotImplementedError

    async def create_label(self, label: NoxusUseCaseLabel) -> str:
        """Crea el label en Noxus y devuelve el id generado alli (noxus_label_id)."""
        raise NotImplementedError

    async def update_label(self, noxus_label_id: str, label: NoxusUseCaseLabel) -> None:
        """Actualiza un label existente en Noxus (identificado por noxus_label_id)."""
        raise NotImplementedError
