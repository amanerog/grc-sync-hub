import httpx

from sinc_amn.config import settings
from sinc_amn.models.use_case import UseCase
from sinc_amn.models.worker import Worker


class NoxusClient:
    """Cliente HTTP contra la API de Noxus.

    A diferencia de Maisa, Noxus expone su propia API de ingesta y asocia el
    caso de uso automaticamente al hacer push (sin label table intermedia ni
    asignacion manual). Contrato exacto del payload pendiente de confirmar con
    el equipo de Noxus (ver ARCHITECTURE.md, seccion "Pendiente de acordar").
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=settings.noxus_base_url,
            headers={"Authorization": f"Bearer {settings.noxus_api_key}"},
        )

    async def push_use_case(self, use_case: UseCase) -> None:
        """Push del caso de uso; Noxus lo asocia automaticamente."""
        raise NotImplementedError

    async def get_updated_workers(self, day) -> list[Worker]:
        """Workers actualizados en Noxus para el dia D-1 dado."""
        raise NotImplementedError
