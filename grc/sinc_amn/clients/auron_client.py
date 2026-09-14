import asyncio
import time
from datetime import date, datetime, timedelta

import httpx

from sinc_amn.config import settings
from sinc_amn.models.use_case import UseCase

# Query API de OpenPages GRC v2 (POST {auron_base_url}/opgrc/api/v2/query),
# confirmada con el equipo de Auron. La respuesta pagina via "offset"/"limit"
# y trae un link "next" mientras queden paginas; cada fila es
# {"fields": [{"name": ..., "value": ...}, ...]}, sin Engagement.Name - por
# eso el tenant se resuelve en el propio WHERE (una query por tenant) en vez
# de leerlo de la respuesta.
_ENGAGEMENT_PREFIX_BY_TENANT = {"maisa": "Maisa", "noxus": "Noxus"}


def _since_condition() -> str | None:
    """WHERE de fecha segun `settings.auron_use_cases_since`.

    "D-1" (default): el dia anterior, calculado en cada llamada (no en el
    arranque del proceso). "All": sin filtro de fecha, se trae todo.
    Cualquier otro valor se usa tal cual como literal de fecha.
    """
    raw = settings.auron_use_cases_since.strip()
    if raw.lower() == "all":
        return None
    if raw.upper() == "D-1":
        raw = (date.today() - timedelta(days=1)).isoformat()
    return f"[Register].[Last Modification Date] > '{raw}'"


def _country_condition() -> str | None:
    """WHERE de pais segun `settings.auron_use_cases_country`.

    Sin setear (None): sin filtro de pais, se traen todos.
    """
    country = settings.auron_use_cases_country
    if not country:
        return None
    return f"[Register].[Santander Fields:Country] = '{country}'"


def _escape_sql_literal(value: str) -> str:
    """Duplica comillas simples, convencion SQL estandar para escaparlas
    dentro de un literal (este lenguaje de query es SQL-like)."""
    single_quote = "'"
    return value.replace(single_quote, single_quote * 2)


_USE_CASE_COLUMNS = (
    "[Register].[Resource ID], [Register].[Name], "
    "[Register].[Santander Fields:aux_Business Entity], "
    "[Register].[Santander Fields:Country], "
    "[Register].[Santander Fields:Owner], "
    "[Register].[Creation Date], "
    "[Register].[Last Modification Date]"
)


def _use_cases_query(tenant: str) -> str:
    prefix = _ENGAGEMENT_PREFIX_BY_TENANT[tenant]
    conditions = [f"[Engagement].[Name] LIKE '{prefix}%'"]
    since_condition = _since_condition()
    if since_condition:
        conditions.append(since_condition)
    country_condition = _country_condition()
    if country_condition:
        conditions.append(country_condition)
    return (
        f"SELECT {_USE_CASE_COLUMNS} "
        "FROM [Register] "
        "JOIN [Engagement] ON PARENT([Register]) "
        f"WHERE {' AND '.join(conditions)}"
    )


def _resource_ids_query(resource_ids: list[str]) -> str:
    """Query por Resource ID explicito, sin filtro de fecha/Engagement -
    usada para reintentar items que fallaron y pudieron salir de la
    ventana de `_since_condition` (ver
    AuronClient.get_use_cases_by_resource_ids).

    TODO: la sintaxis `IN (...)` no esta confirmada contra una respuesta
    real (los ejemplos vistos solo usan `=`/`LIKE`/`>` con un unico valor)
    - revisar si hace falta una cadena de `OR [Register].[Resource ID] =
    '...'` en su lugar.
    """
    escaped_ids = ", ".join(f"'{_escape_sql_literal(rid)}'" for rid in resource_ids)
    return (
        f"SELECT {_USE_CASE_COLUMNS} "
        "FROM [Register] "
        f"WHERE [Register].[Resource ID] IN ({escaped_ids})"
    )


_TOKEN_EXPIRY_BUFFER_SECONDS = 60


class AuronClient:
    """Cliente HTTP contra la API de Auron (OpenPages, dentro de la cuenta SaaS de IBM).

    Autenticacion en dos pasos:
    1. Se cambia el API key por un token OAuth2 via IBM Cloud IAM
       (POST auron_iam_url, grant_type=apikey). El token se cachea en memoria
       y se renueva cuando esta cerca de expirar (segun `expires_in`).
    2. Las llamadas a OpenPages usan ese token como Bearer, mas el header
       ZEN-Service-Instance-Id.

    Todas las creaciones/asociaciones de Use Case y Agent se hacen sobre
    OpenPages (WxG/WxO son solo consumidores en la misma cuenta SaaS, no
    reciben llamadas de este cliente).
    """

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=settings.auron_base_url,
            timeout=settings.auron_http_timeout_seconds,
        )
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()

    async def _get_access_token(self) -> str:
        async with self._token_lock:
            if self._token and time.monotonic() < self._token_expires_at:
                return self._token

            response = await self._client.post(
                settings.auron_iam_url,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                    "apikey": settings.auron_api_key,
                },
            )
            response.raise_for_status()
            payload = response.json()

            self._token = payload["access_token"]
            self._token_expires_at = (
                time.monotonic() + payload["expires_in"] - _TOKEN_EXPIRY_BUFFER_SECONDS
            )
            return self._token

    async def _auth_headers(self) -> dict:
        token = await self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "ZEN-Service-Instance-Id": settings.auron_zen_instance_id,
        }

    async def get_use_cases(self, tenants: list[str]) -> list[UseCase]:
        """Casos de uso de los tenants dados, filtrados por fecha en el propio
        WHERE segun `settings.auron_use_cases_since` (ver `_since_condition`).
        """
        headers = await self._auth_headers()
        use_cases: list[UseCase] = []
        for tenant in tenants:
            statement = _use_cases_query(tenant)
            rows = await self._paginate_query(statement, headers)
            use_cases.extend(self._parse_use_case(row, tenant) for row in rows)
        return use_cases

    async def get_use_cases_by_resource_ids(
        self, resource_ids: list[str], tenant: str
    ) -> list[UseCase]:
        """Casos de uso puntuales por Resource ID, sin filtro de fecha ni de
        Engagement - pensado para reintentar items que fallaron en un run
        anterior y pudieron salir de la ventana `settings.auron_use_cases_since`
        (ver `UseCaseSyncFailureRepository`/`UseCaseSyncService`). El
        `tenant` se pasa explicito porque ya se conoce de cuando se registro
        el fallo originalmente (esta query no filtra por Engagement, asi que
        no hay forma de derivarlo de la respuesta).
        """
        if not resource_ids:
            return []
        headers = await self._auth_headers()
        statement = _resource_ids_query(resource_ids)
        rows = await self._paginate_query(statement, headers)
        return [self._parse_use_case(row, tenant) for row in rows]

    async def _paginate_query(self, statement: str, headers: dict) -> list[dict]:
        rows: list[dict] = []
        offset = 0

        while True:
            response = await self._client.post(
                settings.auron_use_cases_path,
                headers=headers,
                json={
                    "statement": statement,
                    "offset": offset,
                    "case_insensitive": False,
                    "honor_primary": False,
                },
            )
            response.raise_for_status()
            payload = response.json()

            page_rows = payload.get("rows", [])
            rows.extend(page_rows)
            if not payload.get("next"):
                break
            offset += payload.get("limit") or len(page_rows) or 1

        return rows

    @staticmethod
    def _parse_use_case(row: dict, tenant: str) -> UseCase:
        # field.get("value") (no field["value"]): cuando un campo personalizado
        # esta vacio en OpenPages, la fila puede omitir la clave "value" del
        # todo en vez de traerla vacia/null.
        values = {field["name"]: field.get("value") for field in row["fields"]}
        return UseCase(
            resource_id=values["Resource ID"],
            name=values["Name"],
            tenant=tenant,
            # .get() (no []): a diferencia de Resource ID/Name/Creation Date/
            # Last Modification Date, no tenemos confirmado que estos campos
            # personalizados vengan siempre rellenos para todos los registros.
            entity=values.get("Santander Fields:aux_Business Entity"),
            owner=values.get("Santander Fields:Owner"),
            created_at=datetime.fromisoformat(values["Creation Date"]),
            updated_at=datetime.fromisoformat(values["Last Modification Date"]),
        )

    async def get_use_case_content(self, resource_id: str) -> dict:
        """GET /grc/api/contents/{resource_id} - detalle completo de un caso de uso.

        No lo necesita "Funcionalidad 1" (solo usa Resource ID/Name), se deja
        implementado para cuando haga falta leer campos concretos.
        """
        headers = await self._auth_headers()
        response = await self._client.get(
            f"/grc/api/contents/{resource_id}", headers=headers
        )
        response.raise_for_status()
        return response.json()

    async def update_use_case(
        self,
        resource_id: str,
        name: str,
        description: str,
        fields: dict | None = None,
    ) -> dict:
        """PUT /grc/api/contents/{resource_id} - actualiza un caso de uso en OpenPages.

        No la requiere "Funcionalidad 1" (solo lee), se deja implementada para
        cuando haga falta escribir de vuelta en OpenPages.
        """
        headers = await self._auth_headers()
        response = await self._client.put(
            f"/grc/api/contents/{resource_id}",
            headers=headers,
            json={"name": name, "description": description, "fields": fields or {}},
        )
        response.raise_for_status()
        return response.json()

    async def create_content(self, payload: dict) -> dict:
        """POST /grc/api/contents - crea un recurso generico en OpenPages.

        Confirmado via ejemplo real (coleccion Postman "IBM Open Pages",
        "Create an AI Use Case"/"Create an AI Agent"): mismo endpoint para
        cualquier tipo de recurso, distinguido por `typeDefinitionId` dentro
        del propio `payload` (94 = AI Use Case, 156 = Agent en el ejemplo
        visto - sin confirmar si estos ids son estables entre entornos/
        tenants). El resto del payload tipico incluye `name`,
        `parentFolderId` y `fields.field` (lista de
        `{"id", "dataType", "hasChanged", "value"}` o `{"enumValue": {"name"}}`
        para campos de tipo enum).

        Bloque de construccion generico para `create_agent` (pendiente, ver
        TODOs mas abajo); no usado todavia por ningun flujo real.
        """
        headers = await self._auth_headers()
        response = await self._client.post(
            "/grc/api/contents", headers=headers, json=payload
        )
        response.raise_for_status()
        return response.json()

    async def associate(
        self,
        resource_id: str,
        target_id: str,
        association_definition_id: str,
        association_type: str,
    ) -> None:
        """POST /grc/api/contents/{resource_id}/associations - asocia dos recursos.

        Confirmado via ejemplo real: body es una lista con un unico elemento
        `{"id": target_id, "associationDefinitionId": ..., "type": "PARENT"|"CHILD"}`.
        Ejemplos vistos: Use Case -> Business Entity (`associationDefinitionId
        "690"`, type `"PARENT"`), Use Case -> AI solution Maisa (`"64"`,
        `"CHILD"`), Agent -> Use Case (`"966"`, `"PARENT"`) - ninguno confirmado
        estable entre entornos, se pasan como parametro en vez de fijarlos aqui.

        Bloque de construccion generico para `create_agent`/`update_agent`
        (pendiente, ver TODOs mas abajo); no usado todavia por ningun flujo
        real.
        """
        headers = await self._auth_headers()
        response = await self._client.post(
            f"/grc/api/contents/{resource_id}/associations",
            headers=headers,
            json=[
                {
                    "id": target_id,
                    "associationDefinitionId": association_definition_id,
                    "type": association_type,
                }
            ],
        )
        response.raise_for_status()

    async def get_agent_by_worker_id(self, worker_id: str) -> dict | None:
        """Busca el Agent en OpenPages cuya tag worker_id coincide, o None.

        worker_id (de Maisa/Noxus) no es el resource_id/agent_id de OpenPages:
        se guarda como campo personalizado ("tag") en el Agent
        (`settings.auron_agent_worker_id_field_id`, confirmado = "3658",
        "Santander-Fields-Agent:PlatformAgentID"), y hay que localizarlo por
        ese campo, no por ID directo.

        TODO: placeholder. Pendiente el endpoint real de busqueda por campo
        (probablemente el mismo mecanismo de consulta masiva que
        get_use_cases, filtrando por field id "3658" en vez de por
        Engagement) - ningun ejemplo real visto hasta ahora es de busqueda,
        solo de creacion.
        """
        raise NotImplementedError

    async def create_agent(
        self,
        worker_id: str,
        use_case_id: str,
        tenant: str,
        name: str | None,
        description: str | None,
        use_case_owner: str | None,
        agent_owner: str | None,
    ) -> dict:
        """Da de alta un nuevo Agent en OpenPages y lo enlaza al caso de uso.

        Sin workspace_id (confirmado): el workspace_id del `Worker` no es un
        dato del Agent, vive en el propio caso de uso (Noxus; Maisa no tiene
        workspace_id asociado) - la creacion/actualizacion del caso de uso es
        manual y fuera de alcance del microservicio (ver paso 1 del Flujo 1
        en ARCHITECTURE.md), asi que create_agent/update_agent no lo
        necesitan ni lo escriben.

        El enlace a use_case_id es el campo `primaryParentId` del propio
        payload de creacion (confirmado via dos ejemplos reales, `POST
        /grc/api/contents` con `primaryParentId: "<use_case_resource_id>"`,
        sin `parentFolderId`). `associate` sigue siendo valido como bloque
        generico para otras asociaciones (p.ej. Use Case -> Business Entity,
        Use Case -> AI solution), solo dejo de aplicar a este enlace
        concreto.

        `name`/`description` van SOLO como claves de nivel superior, no
        tambien dentro de `fields.field` - un ejemplo completo real de
        creacion de Agent (con los 5 campos personalizados confirmados, ver
        abajo) no incluye entradas para 57/59 en `fields.field`. Confirmado
        que sus valores reales se recuperan de Maisa/Noxus al sincronizar
        (`worker.agent_name`/`worker.agent_description`, ver
        `models/worker.py`), no se generan aqui - solo el prefijo `[Agent
        Maisa]`/`[Agent Noxus]` de `name` lo añade este metodo, usando
        `tenant` (mismo mapeo que `_ENGAGEMENT_PREFIX_BY_TENANT`). Sin
        confirmar: que hacer si `name`/`description` llegan `None` (Maisa/
        Noxus podria no darlos siempre rellenos).

        Los 5 campos personalizados confirmados por ese mismo ejemplo real:
        - `"3658"` ("Santander-Fields-Agent:PlatformAgentID", worker_id, tag
          de busqueda) - unico ya resuelto del todo.
        - `"3261"` ("Santander Fields:Owner") = `use_case_owner` - Owner del
          **Use Case** al que se enlaza el Agent, no un owner propio del
          Agent. Confirmado: se persiste en la tabla intermedia de cada
          tenant durante Flujo 1 (`UseCaseLabel.owner`/
          `NoxusUseCaseLabel.owner`), y el caller (`WorkerSyncService`) lo
          lee de ahi via `get_by_resource_id` - sin GET adicional a
          OpenPages, para Maisa y Noxus por igual.
        - `"3293"` ("Creator of the AI Agent") = `agent_owner` - confirmado
          que es el owner del propio Agent (distinto del anterior),
          recuperado de Maisa/Noxus al sincronizar (`worker.agent_owner`).
        - `"3290"` ("Version id of the provider") - dato de Maisa/Noxus no
          presente en el modelo `Worker` actual.
        - `"3405"` ("Identifier of the cloud account... en Development") -
          dato de Maisa/Noxus no presente en el modelo `Worker` actual.

        La implementacion final sera basicamente:
        ```
        prefix = _ENGAGEMENT_PREFIX_BY_TENANT[tenant]  # "Maisa" | "Noxus"
        create_content({
            "name": f"[Agent {prefix}] {name}",
            "description": description,
            "typeDefinitionId": settings.auron_agent_type_definition_id,
            "primaryParentId": use_case_id,
            "fields": {"field": [
                {"id": settings.auron_agent_worker_id_field_id,
                 "dataType": "STRING_TYPE", "hasChanged": True, "value": worker_id},
                {"id": "3261", "dataType": "STRING_TYPE", "hasChanged": True, "value": use_case_owner},
                {"id": "3293", "dataType": "STRING_TYPE", "hasChanged": True, "value": agent_owner},
                {"id": "3290", "dataType": "STRING_TYPE", "hasChanged": True, "value": provider_version_id},
                {"id": "3405", "dataType": "STRING_TYPE", "hasChanged": True, "value": cloud_account_id},
            ]},
        })
        ```

        TODO: placeholder. Bloqueado por datos que el `Worker`/Flujo 2 no
        traen hoy: `provider_version_id`, `cloud_account_id` (del contrato
        real de Maisa/Noxus, ver TODO en `models/worker.py`).
        """
        raise NotImplementedError

    async def update_agent(
        self,
        agent_id: str,
        use_case_id: str,
        tenant: str,
        name: str | None,
        description: str | None,
        use_case_owner: str | None,
        agent_owner: str | None,
    ) -> dict:
        """Actualiza un Agent existente en OpenPages (enlace a use case y,
        si cambiaron en origen, name/description/owners).

        Sin workspace_id (ver nota en `create_agent`): no es un dato del
        Agent. Para el enlace a use_case_id: sin confirmar si
        `primaryParentId` se puede cambiar en un PUT igual que un `field`
        normal (ningun ejemplo visto es de actualizacion, solo de creacion) -
        si no se puede, podria hacer falta volver a `associate` para este
        caso concreto (re-vincular un Agent ya existente a otro use case).

        TODO: placeholder. Bloqueado por la duda de `primaryParentId` en PUT
        explicada arriba, mas los mismos datos que create_agent
        (`provider_version_id`/`cloud_account_id`).
        """
        raise NotImplementedError
