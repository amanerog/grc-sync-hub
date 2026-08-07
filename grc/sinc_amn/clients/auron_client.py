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
        "SELECT [Register].[Resource ID], [Register].[Name], "
        "[Register].[Santander Fields:ECB AI Category], "
        "[Register].[Santander Fields:Country], "
        "[Register].[Last Modification Date] "
        "FROM [Register] "
        "JOIN [Engagement] ON PARENT([Register]) "
        f"WHERE {' AND '.join(conditions)}"
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
            use_cases.extend(await self._fetch_tenant_use_cases(tenant, headers))
        return use_cases

    async def _fetch_tenant_use_cases(
        self, tenant: str, headers: dict
    ) -> list[UseCase]:
        statement = _use_cases_query(tenant)
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

        return [self._parse_use_case(row, tenant) for row in rows]

    @staticmethod
    def _parse_use_case(row: dict, tenant: str) -> UseCase:
        values = {field["name"]: field["value"] for field in row["fields"]}
        return UseCase(
            resource_id=values["Resource ID"],
            name=values["Name"],
            tenant=tenant,
            # .get() (no []): a diferencia de Resource ID/Name/Last
            # Modification Date, no tenemos confirmado que este campo
            # personalizado venga siempre relleno para todos los registros.
            entity=values.get("Santander Fields:ECB AI Category"),
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

    async def get_agent_by_worker_id(self, worker_id: str) -> dict | None:
        """Busca el Agent en OpenPages cuya tag worker_id coincide, o None.

        worker_id (de Maisa/Noxus) no es el resource_id/agent_id de OpenPages:
        se guarda como campo personalizado ("tag") en el Agent, y hay que
        localizarlo por ese campo, no por ID directo.

        TODO: placeholder. Pendiente el endpoint real de busqueda por campo
        (probablemente el mismo mecanismo de consulta masiva que
        get_use_cases, filtrando por el campo `settings.auron_agent_worker_id_field_id`
        en vez de por Engagement) y confirmar dicho field id con el equipo de Auron.
        """
        raise NotImplementedError

    async def create_agent(
        self, worker_id: str, workspace_id: str, use_case_id: str
    ) -> dict:
        """Da de alta un nuevo Agent en OpenPages.

        El payload debe incluir la tag worker_id (campo personalizado) y el
        enlace al use_case_id (confirmado: es un campo dentro del propio
        payload del Agent, no una llamada de asociacion aparte).

        TODO: placeholder. Los ejemplos reales que tenemos (get/update) son
        sobre un recurso ya existente (`/grc/api/contents/{id}`); falta el
        endpoint de creacion (POST) y los field id de
        `settings.auron_agent_worker_id_field_id` /
        `settings.auron_agent_use_case_field_id`.
        """
        raise NotImplementedError

    async def update_agent(
        self, agent_id: str, workspace_id: str, use_case_id: str
    ) -> dict:
        """Actualiza un Agent existente en OpenPages (workspace + enlace a use case).

        Usara PUT /grc/api/contents/{agent_id} igual que update_use_case, una
        vez se confirmen los field id de worker_id/use_case (ver create_agent).

        TODO: placeholder.
        """
        raise NotImplementedError
