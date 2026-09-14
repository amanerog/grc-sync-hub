import json
from datetime import date, datetime, timedelta, timezone

import httpx

from sinc_amn.clients.auron_client import (
    AuronClient,
    _country_condition,
    _escape_sql_literal,
    _since_condition,
)
from sinc_amn.config import settings

TOKEN_URL = settings.auron_iam_url


def test_default_client_uses_configured_timeout(monkeypatch):
    monkeypatch.setattr(settings, "auron_http_timeout_seconds", 45.0)

    auron = AuronClient()

    assert auron._client.timeout == httpx.Timeout(45.0)


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
    owner: str = "elena.martindiego@example.com",
    creation_date: str = "2026-06-01T09:00:00.000+02:00",
) -> dict:
    return {
        "fields": [
            {"name": "Resource ID", "value": resource_id},
            {"name": "Name", "value": name},
            {"name": "Santander Fields:aux_Business Entity", "value": entity},
            {"name": "Santander Fields:Country", "value": "ESP"},
            {"name": "Santander Fields:Owner", "value": owner},
            {"name": "Creation Date", "value": creation_date},
            {"name": "Last Modification Date", "value": last_modification_date},
        ]
    }


def test_parse_use_case_tolerates_field_without_value_key():
    # OpenPages puede omitir la clave "value" del todo (no solo dejarla
    # vacia/null) cuando un campo personalizado no esta relleno.
    row = {
        "fields": [
            {"name": "Resource ID", "value": "11075"},
            {"name": "Name", "value": "Transaction Analysis"},
            {"name": "Santander Fields:aux_Business Entity"},
            {"name": "Santander Fields:Owner"},
            {"name": "Creation Date", "value": "2026-06-01T09:00:00.000+02:00"},
            {"name": "Last Modification Date", "value": "2026-07-20T17:29:20.000+02:00"},
        ]
    }

    use_case = AuronClient._parse_use_case(row, tenant="maisa")

    assert use_case.resource_id == "11075"
    assert use_case.entity is None
    assert use_case.owner is None


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
    assert all(uc.owner == "elena.martindiego@example.com" for uc in use_cases)
    assert use_cases[0].created_at == datetime(
        2026, 6, 1, 9, 0, 0, tzinfo=timezone(timedelta(hours=2))
    )
    assert use_cases[0].updated_at == datetime(
        2026, 7, 20, 17, 29, 20, tzinfo=timezone(timedelta(hours=2))
    )
    # 2 paginas para maisa (offset 0 con "next", offset 1 sin "next") + 1 para noxus.
    assert len(calls) == 3
    assert calls[0]["offset"] == 0
    assert calls[1]["offset"] == 1
    for call in calls:
        statement = call["statement"]
        assert "[Register].[Santander Fields:aux_Business Entity]" in statement
        assert "[Register].[Santander Fields:Owner]" in statement
        assert "[Register].[Creation Date]" in statement
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


def test_escape_sql_literal_doubles_single_quotes():
    assert _escape_sql_literal("O'Brien") == "O''Brien"
    assert _escape_sql_literal("RES-1") == "RES-1"


async def test_get_use_cases_by_resource_ids_queries_without_date_or_engagement_filter(
    monkeypatch,
):
    monkeypatch.setattr(settings, "auron_use_cases_since", "2026-07-15")
    monkeypatch.setattr(settings, "auron_use_cases_country", "ESP")
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(
                200, json={"access_token": "tok-123", "expires_in": 3600}
            )
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(
            200,
            json={
                "rows": [
                    _row("11075", "Transaction Analysis", "2026-07-20T17:29:20.000+02:00")
                ],
                "offset": 0,
                "limit": 50,
            },
        )

    http_client = httpx.AsyncClient(
        base_url=settings.auron_base_url, transport=httpx.MockTransport(handler)
    )
    auron = AuronClient(client=http_client)

    use_cases = await auron.get_use_cases_by_resource_ids(["11075"], tenant="maisa")

    assert [uc.resource_id for uc in use_cases] == ["11075"]
    # El tenant viene del parametro, no de la respuesta (esta query no
    # filtra ni selecciona Engagement).
    assert use_cases[0].tenant == "maisa"
    assert len(calls) == 1
    statement = calls[0]["statement"]
    assert "[Register].[Resource ID] IN ('11075')" in statement
    # Sin filtro de fecha/pais ni JOIN de Engagement, aunque esten configurados.
    assert "Last Modification Date] >" not in statement
    assert "Santander Fields:Country] =" not in statement
    assert "Engagement" not in statement

    await http_client.aclose()


async def test_get_use_cases_by_resource_ids_returns_empty_without_http_call():
    http_client = httpx.AsyncClient(base_url=settings.auron_base_url)
    auron = AuronClient(client=http_client)

    use_cases = await auron.get_use_cases_by_resource_ids([], tenant="maisa")

    assert use_cases == []

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


def _make_create_content_client(captured: list[dict]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(
                200, json={"access_token": "tok-123", "expires_in": 3600}
            )

        assert request.method == "POST"
        assert request.url.path == "/grc/api/contents"
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "35378"})

    return httpx.AsyncClient(
        base_url=settings.auron_base_url, transport=httpx.MockTransport(handler)
    )


async def test_create_content_posts_payload_as_is():
    captured: list[dict] = []
    http_client = _make_create_content_client(captured)
    auron = AuronClient(client=http_client)
    payload = {"name": "[Agent Noxus] Prueba", "typeDefinitionId": "156"}

    result = await auron.create_content(payload)

    assert result == {"id": "35378"}
    assert captured == [payload]

    await http_client.aclose()


def _make_associate_client(captured: list[dict]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(
                200, json={"access_token": "tok-123", "expires_in": 3600}
            )

        assert request.method == "POST"
        assert request.url.path == "/grc/api/contents/35378/associations"
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=[])

    return httpx.AsyncClient(
        base_url=settings.auron_base_url, transport=httpx.MockTransport(handler)
    )


async def test_associate_posts_single_element_list_with_expected_shape():
    captured: list[dict] = []
    http_client = _make_associate_client(captured)
    auron = AuronClient(client=http_client)

    await auron.associate(
        resource_id="35378",
        target_id="35375",
        association_definition_id="966",
        association_type="PARENT",
    )

    assert captured == [
        [{"id": "35375", "associationDefinitionId": "966", "type": "PARENT"}]
    ]

    await http_client.aclose()
