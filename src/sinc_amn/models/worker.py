from datetime import date

from pydantic import BaseModel


class Worker(BaseModel):
    """Worker actualizado en D-1, origen: Maisa/Noxus."""

    worker_id: str
    workspace_id: str
    use_case_id: str | None = None  # None => se enlaza al caso de uso generico
    updated_at: date
    # TODO: completar con el resto de campos del contrato real de Maisa/Noxus
