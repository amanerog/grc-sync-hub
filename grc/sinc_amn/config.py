from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuracion del microservicio, poblada desde variables de entorno.

    Cada entidad se despliega con su propio juego de valores (credenciales de
    Auron/Maisa/Noxus y su generic_use_case_id).
    """

    # Auron (OpenPages) - autenticacion en dos pasos: apikey -> token IAM
    auron_base_url: str
    auron_api_key: str
    auron_iam_url: str = "https://iam.cloud.ibm.com/identity/token"
    auron_zen_instance_id: str
    # TODO: confirmar el path real del endpoint de consulta masiva (el slide
    # solo indica "...."; get/update de un recurso concreto SI esta confirmado
    # via /grc/api/contents/{resource_id}, ver AuronClient).
    auron_use_cases_path: str = "/api/v1/register-query"

    # Maisa
    maisa_base_url: str
    maisa_api_key: str

    # Noxus
    noxus_base_url: str
    noxus_api_key: str

    # Flujo 2: caso de uso generico para workers sin use_case_id
    generic_use_case_id: str
    # Flujo 2: field id de los campos personalizados del Agent en OpenPages.
    # Pendientes de confirmar con el equipo de Auron (ver AuronClient).
    auron_agent_worker_id_field_id: str | None = None
    auron_agent_use_case_field_id: str | None = None

    # Flujo 1: backend de checkpoint (pendiente de decidir: dynamodb/rds/configmap)
    checkpoint_backend: str = "configmap"

    # Flujo 1 - Funcionalidad 1: tabla intermedia OpenPages<->Maisa (RDS Postgres)
    intermediate_db_dsn: str
    # organizationId con el que Maisa identifica a esta entidad/entorno
    maisa_organization_id: str

    class Config:
        env_prefix = "SINC_AMN_"


settings = Settings()
