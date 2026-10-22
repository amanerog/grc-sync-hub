from datetime import date

from pydantic import BaseModel

from sinc_amn.models.use_case import Tenant


class Worker(BaseModel):
    """Worker actualizado en D-1, origen: Maisa/Noxus."""

    worker_id: str
    workspace_id: str
    tenant: Tenant  # origen (maisa/noxus) - lo fija quien construya el Worker
    use_case_id: str | None = None  # None => se enlaza al caso de uso generico
    updated_at: date
    # Confirmado: el name/description reales del Agent en OpenPages se
    # recuperan de Maisa/Noxus al sincronizar, no se generan aqui (ver
    # AuronClient.create_agent). Opcionales porque get_updated_workers sigue
    # sin implementar - no confirmado si el proveedor los da siempre rellenos.
    agent_name: str | None = None
    agent_description: str | None = None
    # "Creator of the AI Agent" (field "3293") - confirmado que es el owner
    # del propio Agent (distinto del owner del Use Case, que vive en la
    # tabla intermedia via UseCaseLabel.owner, no aqui), tambien recuperado
    # de Maisa/Noxus al sincronizar.
    agent_owner: str | None = None
    # "Version id of the provider" (field "3290") - confirmado que viene de
    # Maisa/Noxus al sincronizar, igual que agent_name/agent_description.
    # Opcional porque get_updated_workers sigue sin implementar - no
    # confirmado si el proveedor lo da siempre relleno.
    provider_version_id: str | None = None
    # Id tecnico del modelo LLM de la version desplegada (Maisa:
    # `worker.model.name`). Opcional: hay versiones sin modelo. Destino:
    # field "3408" (Santander Fields:API ID) del caso de uso, no del Agent -
    # sin enviar hasta implementar el PUT al caso de uso.
    model_id: str | None = None
    # TODO: completar con el resto de campos del contrato real de Maisa/Noxus,
    # si aparecen mas al confirmarlo. El field "3405" (cuenta cloud, en el
    # caso de uso) NO es un dato de Worker - settings.aws_account_id.
