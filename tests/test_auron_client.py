import json
from datetime import date, datetime, timedelta, timezone

import httpx

from sinc_amn.clients.auron_client import (
    AuronClient,
    _country_condition,
    _since_condition,
)
from sinc_amn.config import settings

TOKEN_URL = settings.auron_iam_url


def test_since_condition_defaults_to_d_minus_1(monkeypatch):
    monkeypatch.setattr(settings, "auron_use_cases_since", "D-1")

    yesterday = (date.today() - timedelta(days=1)).isoformat()

    assert _since_condition() == (
        f"[Register].[Last Modification Date] > '{yesterday}'"
    )


def test_since_condition_all_disables_date_filter(monkeypatch):
    monkeypatch.setattr(settings, "auron_use_cases_since", "All")

    assert _since_condition() is None


def test_since_condition_uses_explicit_value(monkeypatch):
    monkeypatch.setattr(settings, "auron_use_cases_since", "2026-01-01")

    assert (
        _since_condition() == "[Register].[Last Modification Date] > '2026-01-01'"
    )


def test_country_condition_is_none_when_not_set(monkeypatch):
    monkeypatch.setattr(settings, "auron_use_cases_country", None)

    assert _country_condition() is None


def test_country_condition_uses_configured_value(monkeypatch):
    monkeypatch.setattr(settings, "auron_use_cases_country", "ESP")

    assert (
        _country_condition()
        == "[Register].[Santander Fields:Country] = 'ESP'"
    )


def _row(
    resource_id: str,
    name: str,
    last_modification_date: str,
    entity: str = "AI System",
) -> dict:
    return {
        "fields": [
            {"name": "Resource ID", "value": resource_id},
            {"name": "Name", "value": name},
            {"name": "Santander Fields:ECB AI Category", "value": entity},
            {"name": "Santander Fields:Country", "value": "ESP"},
            {"name": "Last Modification Date", "value": last_modification_date},
        ]
    }


def _make_use_cases_client(calls: list[dict]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(
                200, json={"access_token": "tok-123", "expires_in": 3600}
            )

        assert request.method == "POST"
        assert request.url.path == settings.auron_use_cases_path
        body = json.loads(request.content)
        calls.append(body)
        statement = body["statement"]
        offset = body["offset"]

        if "'Maisa%'" in statement:
            if offset == 0:
                return httpx.Response(
                    200,
                    json={
                        "rows": [
                            _row(
                                "11075",
                                "Transaction Analysis",
                                "2026-07-20T17:29:20.000+02:00",
                            )
                        ],
                        "offset": 0,
                        "limit": 1,
                        "next": {"href": "https://auron.test/opgrc/api/v2/query?offset=1"},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "rows": [
                        _row("11281", "Prueba Alex 1", "2026-07-16T09:00:00.000+02:00"),
                        _row(
                            "11387",
                            "Prueba paso workflow",
                            "2026-07-01T09:00:00.000+02:00",
                        ),
                    ],
                    "offset": 1,
                    "limit": 2,
                },
            )
        if "'Noxus%'" in statement:
            return httpx.Response(200, json={"rows": [], "offset": 0, "limit": 50})
        raise AssertionError(f"unexpected statement: {statement}")

    return httpx.AsyncClient(
        base_url=settings.auron_base_url, transport=httpx.MockTransport(handler)
    )


async def test_get_use_cases_queries_each_tenant_with_since_and_paginates(
    monkeypatch,
):
    monkeypatch.setattr(settings, "auron_use_cases_since", "2026-07-15")
    monkeypatch.setattr(settings, "auron_use_cases_country", "ESP")
    calls: list[dict] = []
    http_client = _make_use_cases_client(calls)
    auron = AuronClient(client=http_client)

    use_cases = await auron.get_use_cases(tenants=["maisa", "noxus"])

    assert [uc.resource_id for uc in use_cases] == ["11075", "11281", "11387"]
    assert [uc.name for uc in use_cases] == [
        "Transaction Analysis",
        "Prueba Alex 1",
        "Prueba paso workflow",
    ]
    assert all(uc.tenant == "maisa" for uc in use_cases)
    assert all(uc.entity == "AI System" for uc in use_cases)
    assert use_cases[0].updated_at == datetime(
        2026, 7, 20, 17, 29, 20, tzinfo=timezone(timedelta(hours=2))
    )
    # 2 paginas para maisa (offset 0 con "next", offset 1 sin "next") + 1 para noxus.
    assert len(calls) == 3
    assert calls[0]["offset"] == 0
    assert calls[1]["offset"] == 1
    for call in calls:
        statement = call["statement"]
        assert "[Register].[Santander Fields:ECB AI Category]" in statement
        assert "[Register].[Last Modification Date] > '2026-07-15'" in statement
        assert "[Register].[Santander Fields:Country] = 'ESP'" in statement

    await http_client.aclose()


async def test_get_use_cases_without_country_omits_country_filter(monkeypatch):
    monkeypatch.setattr(settings, "auron_use_cases_country", None)
    calls: list[dict] = []
    http_client = _make_use_cases_client(calls)
    auron = AuronClient(client=http_client)

    await auron.get_use_cases(tenants=["maisa", "noxus"])

    assert calls
    for call in calls:
        # La columna se sigue seleccionando (igual que en el ejemplo
        # confirmado), pero no debe aparecer como condicion del WHERE.
        assert "[Register].[Santander Fields:Country] =" not in call["statement"]

    await http_client.aclose()


def _make_content_client(calls: list[str]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))

        if str(request.url) == TOKEN_URL:
            return httpx.Response(
                200, json={"access_token": "tok-123", "expires_in": 3600}
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


async def test_get_use_case_content_and_update_use_case():
    calls: list[str] = []
    http_client = _make_content_client(calls)
    auron = AuronClient(client=http_client)

    content = await auron.get_use_case_content("RES-1")
    updated = await auron.update_use_case("RES-1", name="X", description="Y")

    assert content == {"resourceId": "RES-1", "name": "Caso 1"}
    assert updated["name"] == "Actualizado"

    await http_client.aclose()
