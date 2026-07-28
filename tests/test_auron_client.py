from datetime import datetime, timezone

import httpx

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.config import settings

TOKEN_URL = settings.auron_iam_url


def _make_http_client(calls: list[str]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))

        if str(request.url) == TOKEN_URL:
            return httpx.Response(
                200, json={"access_token": "tok-123", "expires_in": 3600}
            )
        if request.url.path == settings.auron_use_cases_path:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "resourceId": "RES-1",
                            "name": "Caso 1",
                            "engagementName": "Maisa Corp",
                            "updatedAt": "2026-07-20T00:00:00+00:00",
                        },
                        {
                            "resourceId": "RES-2",
                            "name": "Caso 2",
                            "engagementName": "Noxus Corp",
                            "updatedAt": "2026-07-01T00:00:00+00:00",
                        },
                    ]
                },
            )
        if request.url.path == "/grc/api/contents/RES-1":
            if request.method == "GET":
                return httpx.Response(
                    200, json={"resourceId": "RES-1", "name": "Caso 1"}
                )
            if request.method == "PUT":
                return httpx.Response(
                    200, json={"resourceId": "RES-1", "name": "Actualizado"}
                )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    return httpx.AsyncClient(
        base_url=settings.auron_base_url, transport=httpx.MockTransport(handler)
    )


async def test_get_use_cases_filters_by_tenant_and_since_and_caches_token():
    calls: list[str] = []
    http_client = _make_http_client(calls)
    auron = AuronClient(client=http_client)
    since = datetime(2026, 7, 15, tzinfo=timezone.utc)

    first = await auron.get_use_cases(since=since, tenants=["maisa", "noxus"])
    second = await auron.get_use_cases(since=since, tenants=["maisa", "noxus"])

    assert [uc.resource_id for uc in first] == ["RES-1"]
    assert first[0].tenant == "maisa"
    assert second == first
    # El segundo get_use_cases reutiliza el token cacheado: una sola llamada al IAM.
    assert calls.count(TOKEN_URL) == 1

    await http_client.aclose()


async def test_get_use_case_content_and_update_use_case():
    calls: list[str] = []
    http_client = _make_http_client(calls)
    auron = AuronClient(client=http_client)

    content = await auron.get_use_case_content("RES-1")
    updated = await auron.update_use_case("RES-1", name="X", description="Y")

    assert content == {"resourceId": "RES-1", "name": "Caso 1"}
    assert updated["name"] == "Actualizado"

    await http_client.aclose()
