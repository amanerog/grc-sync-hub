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
    # Endpoint confirmado de consulta masiva (Query API de OpenPages GRC v2).
    auron_use_cases_path: str = "/opgrc/api/v2/query"
    # Umbral de fecha para el WHERE [Register].[Last Modification Date] > ...
    # de la consulta masiva. "D-1" (default): se calcula el dia anterior en
    # cada llamada. "All": no se filtra por fecha, se trae todo. Cualquier
    # otro valor se usa tal cual como literal de fecha en el WHERE.
    auron_use_cases_since: str = "D-1"
    # Filtro opcional por [Register].[Santander Fields:Country] (p.ej. "ESP").
    # Sin setear: no se filtra por pais, se traen todos.
    auron_use_cases_country: str | None = None

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
