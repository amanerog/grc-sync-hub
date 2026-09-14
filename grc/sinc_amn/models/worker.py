from datetime import date

from pydantic import BaseModel


class Worker(BaseModel):
    """Worker actualizado en D-1, origen: Maisa/Noxus."""

    worker_id: str
    workspace_id: str
    use_case_id: str | None = None  # None => se enlaza al caso de uso generico
    updated_at: date
    # TODO: completar con el resto de campos del contrato real de Maisa/Noxus.
    # Confirmado que AuronClient.create_agent los necesita (ver su docstring)
    # para completar el payload real del Agent en OpenPages: nombre del
    # agente segun el proveedor (Maisa/Noxus), version id del proveedor
    # (field "3290") e identificador de la cuenta cloud donde esta
    # desplegado en Development (field "3405"). Ninguno de los tres esta en
    # el modelo todavia.
