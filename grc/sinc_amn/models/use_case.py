from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Tenant = Literal["maisa", "noxus"]


class UseCase(BaseModel):
    """Caso de uso tal y como lo expone OpenPages (Register/Engagement)."""

    resource_id: str  # [Register].[Resource ID] -- clave de correlacion con OpenPages
    name: str  # [Register].[Name]
    tenant: Tenant  # derivado del prefijo de [Engagement].[Name] (Maisa%/Noxus%)
    updated_at: datetime
