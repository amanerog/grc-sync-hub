from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from sinc_amn.models.use_case_label import LabelStatus


class NoxusUseCaseLabel(BaseModel):
    """Registro de la tabla intermedia (Postgres/RDS) que vincula OpenPages con Noxus.

    Mismo diseño que `UseCaseLabel` (Maisa) - confirmado que Noxus tambien
    usa tabla intermedia, no push directo por item (corrige un diseño
    anterior, ver ARCHITECTURE.md) - con dos diferencias confirmadas:
    - `workspace_id`: Noxus si tiene workspace_id asociado al caso de uso
      (Maisa no). Sin confirmar en que paso se rellena - `UseCase` (el
      modelo de origen, OpenPages) no trae hoy un campo workspace_id, asi
      que puede que no este disponible en el momento de la ingesta desde
      OpenPages y haya que completarlo en un paso posterior.
    - `noxus_label_id` (en vez de `maisa_label_id`): id devuelto por Noxus
      al hacer el push, mismo patron de coordinacion que "Funcionalidad *".
    """

    id: UUID
    source_resource_id: str
    name: str
    name_lower: str
    entity: str | None = None  # [Register].[Santander Fields:aux_Business Entity] en Auron
    owner: str | None = None  # [Register].[Santander Fields:Owner] en Auron
    workspace_id: str | None = None  # TODO: confirmar en que paso se rellena
    organization_id: str
    worker_count: int
    status: LabelStatus
    noxus_label_id: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    is_deleted: bool = False
