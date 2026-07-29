from datetime import datetime
from typing import Literal

from pydantic import BaseModel

Tenant = Literal["maisa", "noxus"]


class UseCase(BaseModel):
    """Caso de uso tal y como lo expone OpenPages (Register/Engagement)."""

    resource_id: str  # [Register].[Resource ID] -- clave de correlacion con OpenPages
    name: str  # [Register].[Name]
    tenant: Tenant  # tenant de la query que lo devolvio (WHERE Engagement.Name LIKE '<Tenant>%')
    entity: str | None = None  # [Register].[Santander Fields:ECB AI Category]
    updated_at: datetime  # [Register].[Last Modification Date]
