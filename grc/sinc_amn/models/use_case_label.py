from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

LabelStatus = Literal["new", "modified", "synced", "deprecated"]


class UseCaseLabel(BaseModel):
    """Registro de la tabla intermedia (Postgres/RDS) que vincula OpenPages con Maisa.

    Un registro unico por caso de uso (source_resource_id + organization_id).
    worker_count lo mantiene Maisa (asignacion/desasignacion de workers) y no
    lo toca la ingesta desde OpenPages salvo al crear el registro (arranca a 0).

    status es el mecanismo de coordinacion entre "Funcionalidad 1" (OpenPages
    -> tabla intermedia, deja 'new'/'modified') y "Funcionalidad *" (tabla
    intermedia -> Maisa, consume 'new'/'modified' y deja 'synced').
    maisa_label_id es el id devuelto por Maisa al crear el label (None hasta
    el primer sync exitoso).
    """

    id: UUID
    source_resource_id: str
    name: str
    name_lower: str
    organization_id: str
    worker_count: int
    status: LabelStatus
    maisa_label_id: str | None = None
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
    is_deleted: bool = False
