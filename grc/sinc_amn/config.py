from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Configuracion del microservicio, poblada desde variables de entorno.

    Cada entidad se despliega con su propio juego de valores (credenciales de
    Auron/Maisa/Noxus y su generic_use_case_id).
    """

    # Auron (OpenPages) - autenticacion en dos pasos: apikey -> token IAM
    auron_api_key: str
    auron_iam_url: str = "https://iam.cloud.ibm.com/identity/token"
    auron_zen_instance_id: str
    # Si no se setea, se deriva de auron_zen_instance_id (mismo patron que en
    # todos los ejemplos reales confirmados: <zen_instance_id>.eu-de.
    # openpages.cloud.ibm.com). Se puede fijar explicitamente para forzar
    # otro host/region si alguna entidad/entorno lo necesitara (ver
    # `_default_auron_base_url` mas abajo).
    auron_base_url: str | None = None
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
    # httpx.AsyncClient sin timeout explicito usa 5s por defecto (connect/
    # read/write/pool) - insuficiente para la Query API de OpenPages, que
    # puede tardar mas en consultas grandes. Aplica a todas las llamadas de
    # AuronClient.
    auron_http_timeout_seconds: float = 30.0

    # Maisa
    maisa_base_url: str
    maisa_api_key: str

    # Noxus
    noxus_base_url: str
    noxus_api_key: str

    # Flujo 2: caso de uso generico para workers sin use_case_id
    generic_use_case_id: str
    # Flujo 2: field id de la tag worker_id (campo personalizado del Agent,
    # "Santander-Fields-Agent:PlatformAgentID"). Bloqueante historico de
    # create_agent/get_agent_by_worker_id, ya resuelto.
    auron_agent_worker_id_field_id: str = "3658"
    # typeDefinitionId del tipo "Agent" en OpenPages. Confirmado via dos
    # ejemplos reales independientes con el mismo valor (no se ha visto
    # variar por tenant Maisa/Noxus).
    auron_agent_type_definition_id: str = "156"
    # primaryParentId usado al crear el Use Case generico "Pendiente de
    # regularizar" (typeDefinitionId "94", ver ARCHITECTURE.md). Confirmado
    # que es especifico de entorno: "10135" es el valor real de PRE, valido
    # para pruebas. Falta el de PRO - hay que sobreescribir esta variable al
    # desplegar en ese entorno. Tampoco confirmado si Noxus usa el mismo
    # valor que Maisa (los unicos ejemplos vistos son de Maisa).
    auron_generic_use_case_parent_id: str = "10135"
    # Id del recurso "AI solution" de cada tenant en OpenPages, usado como
    # target_id de AuronClient.associate() al crear el Use Case generico
    # (associationDefinitionId "64", type "CHILD"). Confirmado que Maisa y
    # Noxus usan ids DISTINTOS (no es el mismo recurso).
    auron_maisa_ai_solution_id: str = "11342"
    auron_noxus_ai_solution_id: str = "15327"

    # Flujo 1: backend de checkpoint (pendiente de decidir: dynamodb/rds/configmap)
    checkpoint_backend: str = "configmap"

    # Flujo 1 - Funcionalidad 1: tabla intermedia OpenPages<->Maisa (RDS Postgres)
    intermediate_db_dsn: str
    # organizationId con el que Maisa identifica a esta entidad/entorno
    maisa_organization_id: str
    # Equivalente a maisa_organization_id pero para la tabla intermedia de
    # Noxus (noxus_use_case_labels) - confirmado que Noxus tambien usa tabla
    # intermedia, mismo diseño que Maisa (ver ARCHITECTURE.md). Sin
    # confirmar aun si Noxus tiene un concepto de "organizationId" propio
    # equivalente al de Maisa, ni su valor real - placeholder opcional
    # mientras tanto.
    noxus_organization_id: str | None = None

    class Config:
        env_prefix = "SINC_AMN_"

    @model_validator(mode="after")
    def _default_auron_base_url(self) -> "Settings":
        if not self.auron_base_url:
            self.auron_base_url = (
                f"https://{self.auron_zen_instance_id}.eu-de.openpages.cloud.ibm.com"
            )
        return self


settings = Settings()
