import asyncio
import time
from datetime import datetime, timezone

import httpx

from sinc_amn.config import settings
from sinc_amn.models.use_case import UseCase

# TODO: confirmar con el equipo de Auron el endpoint real y el mecanismo del
# filtro incremental "since" de esta consulta masiva. Body tal cual lo
# documenta el contrato de OpenPages (GET con body JSON) - a diferencia de
# get_use_case_content/update_use_case, este endpoint no ha sido validado
# contra un ejemplo de codigo real.
_USE_CASES_QUERY = (
    "SELECT [Register].[Resource ID], [Register].[Name] "
    "FROM [Register] "
    "JOIN [Engagement] ON PARENT([Register]) "
    "WHERE [Engagement].[Name] LIKE 'Maisa%' OR [Engagement].[Name] LIKE 'Noxus%'"
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
        self._client = client or httpx.AsyncClient(base_url=settings.auron_base_url)
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

    async def get_use_cases(
        self, since: datetime, tenants: list[str]
    ) -> list[UseCase]:
        """Casos de uso creados/actualizados desde `since` para los tenants dados."""
        headers = await self._auth_headers()
        # httpx >=0.28 quito el parametro `json` del atajo `.get()` (GET con
        # body ya no esta soportado ahi); `.request()` si lo mantiene para
        # cualquier verbo, y aqui hace falta: el contrato de OpenPages exige
        # un GET con body JSON para esta consulta masiva.
        response = await self._client.request(
            "GET",
            settings.auron_use_cases_path,
            headers=headers,
            params={"since": since.astimezone(timezone.utc).isoformat()},
            json={"body": _USE_CASES_QUERY},
        )
        response.raise_for_status()
        payload = response.json()

        use_cases = [self._parse_use_case(item) for item in payload.get("items", [])]
        return [uc for uc in use_cases if uc.tenant in tenants and uc.updated_at >= since]

    @staticmethod
    def _parse_use_case(item: dict) -> UseCase:
        engagement_name: str = item["engagementName"]
        tenant = "maisa" if engagement_name.lower().startswith("maisa") else "noxus"
        return UseCase(
            resource_id=item["resourceId"],
            name=item["name"],
            tenant=tenant,
            updated_at=datetime.fromisoformat(item["updatedAt"]),
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
