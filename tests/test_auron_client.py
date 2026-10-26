import json
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest

from sinc_amn.clients import auron_client
from sinc_amn.clients.auron_client import (
    AuronClient,
    _country_condition,
    _escape_sql_literal,
    _field_text,
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


def test_parse_use_case_reads_name_of_enum_fields():
    # aux_Business Entity es un enumerado: OpenPages lo devuelve como objeto.
    entity = {"id": "12025", "name": "Santander Spain", "index": 3, "hidden": False}
    row = _row("11075", "Transaction Analysis", "2026-07-20T17:29:20.000+02:00")
    row["fields"][2]["value"] = entity

    use_case = AuronClient._parse_use_case(row, tenant="maisa")

    assert use_case.entity == "Santander Spain"


def test_field_text_handles_strings_enums_and_lists():
    assert _field_text(None) is None
    assert _field_text("ESP") == "ESP"
    assert _field_text({"id": "1", "name": "A"}) == "A"
    assert _field_text([{"id": "1", "name": "A"}, {"id": "2", "name": "B"}]) == "A, B"
    assert _field_text([]) is None


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

        if "[Engagement].[Resource ID] LIKE '11334'" in statement:
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
        if "[Engagement].[Resource ID] LIKE '15327'" in statement:
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
        assert "[Register].[Santander Fields:Status]" in statement
        assert "[Register].[Creation Date]" in statement
        assert "([Register].[Last Modification Date] > '2026-07-15')" in statement
        assert "([Register].[Santander Fields:Country] = 'ESP')" in statement
        assert "[Engagement].[Name]" not in statement

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


def _make_dissociate_client(captured: list[str]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(
                200, json={"access_token": "tok-123", "expires_in": 3600}
            )

        assert request.method == "DELETE"
        assert request.url.path == "/grc/api/contents/35378/associations"
        captured.append(str(request.url))
        return httpx.Response(200)

    return httpx.AsyncClient(
        base_url=settings.auron_base_url, transport=httpx.MockTransport(handler)
    )


async def test_dissociate_deletes_with_parents_query_param():
    captured: list[str] = []
    http_client = _make_dissociate_client(captured)
    auron = AuronClient(client=http_client)

    await auron.dissociate(resource_id="35378", parent_id="35375")

    assert len(captured) == 1
    assert "parents=35375" in captured[0]

    await http_client.aclose()


async def test_create_agent_posts_expected_payload():
    captured: list[dict] = []
    http_client = _make_create_content_client(captured)
    auron = AuronClient(client=http_client)

    result = await auron.create_agent(
        worker_id="W-1",
        use_case_id="UC-1",
        tenant="noxus",
        name="Agente de prueba",
        description="Descripcion de prueba",
        use_case_owner="owner@example.com",
        agent_owner="agent-owner@example.com",
        provider_version_id="v1.0",
    )

    assert result == {"id": "35378"}
    assert captured == [
        {
            "name": "[Agent Noxus] Agente de prueba",
            "description": "Descripcion de prueba",
            "typeDefinitionId": settings.auron_agent_type_definition_id,
            "primaryParentId": "UC-1",
            "fields": {
                "field": [
                    {
                        "id": "3658",
                        "dataType": "STRING_TYPE",
                        "hasChanged": True,
                        "value": "W-1",
                    },
                    {
                        "id": "3261",
                        "dataType": "STRING_TYPE",
                        "hasChanged": True,
                        "value": "owner@example.com",
                    },
                    {
                        "id": "3293",
                        "dataType": "STRING_TYPE",
                        "hasChanged": True,
                        "value": "agent-owner@example.com",
                    },
                    {
                        "id": "3290",
                        "dataType": "STRING_TYPE",
                        "hasChanged": True,
                        "value": "v1.0",
                    },
                ]
            },
        }
    ]

    await http_client.aclose()


async def test_create_agent_omits_description_when_missing():
    captured: list[dict] = []
    http_client = _make_create_content_client(captured)
    auron = AuronClient(client=http_client)

    await auron.create_agent(
        worker_id="W-1",
        use_case_id="UC-1",
        tenant="maisa",
        name="Agente de prueba",
        description=None,
        use_case_owner=None,
        agent_owner="agent-owner@example.com",
        provider_version_id="v1.0",
    )

    assert "description" not in captured[0]
    assert captured[0]["name"] == "[Agent Maisa] Agente de prueba"

    await http_client.aclose()


async def test_create_agent_raises_when_name_missing():
    http_client = httpx.AsyncClient(base_url=settings.auron_base_url)
    auron = AuronClient(client=http_client)

    with pytest.raises(ValueError):
        await auron.create_agent(
            worker_id="W-1",
            use_case_id="UC-1",
            tenant="maisa",
            name=None,
            description="Descripcion de prueba",
            use_case_owner="owner@example.com",
            agent_owner="agent-owner@example.com",
            provider_version_id="v1.0",
        )

    await http_client.aclose()


async def test_create_agent_raises_when_agent_owner_missing():
    http_client = httpx.AsyncClient(base_url=settings.auron_base_url)
    auron = AuronClient(client=http_client)

    with pytest.raises(ValueError):
        await auron.create_agent(
            worker_id="W-1",
            use_case_id="UC-1",
            tenant="maisa",
            name="Agente de prueba",
            description="Descripcion de prueba",
            use_case_owner="owner@example.com",
            agent_owner=None,
            provider_version_id="v1.0",
        )

    await http_client.aclose()


async def test_create_agent_raises_when_provider_version_id_missing():
    http_client = httpx.AsyncClient(base_url=settings.auron_base_url)
    auron = AuronClient(client=http_client)

    with pytest.raises(ValueError):
        await auron.create_agent(
            worker_id="W-1",
            use_case_id="UC-1",
            tenant="maisa",
            name="Agente de prueba",
            description="Descripcion de prueba",
            use_case_owner="owner@example.com",
            agent_owner="agent-owner@example.com",
            provider_version_id=None,
        )

    await http_client.aclose()


def _make_update_content_client(captured: list[tuple[str, dict]]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(
                200, json={"access_token": "tok-123", "expires_in": 3600}
            )

        assert request.method == "PUT"
        captured.append((request.url.path, json.loads(request.content)))
        return httpx.Response(200, json={"id": "35378"})

    return httpx.AsyncClient(
        base_url=settings.auron_base_url, transport=httpx.MockTransport(handler)
    )


async def test_update_content_puts_payload_as_is():
    captured: list[tuple[str, dict]] = []
    http_client = _make_update_content_client(captured)
    auron = AuronClient(client=http_client)
    payload = {"name": "[Agent Noxus] Prueba"}

    result = await auron.update_content("35378", payload)

    assert result == {"id": "35378"}
    assert captured == [("/grc/api/contents/35378", payload)]

    await http_client.aclose()


async def test_update_agent_puts_expected_payload_without_primary_parent_id():
    captured: list[tuple[str, dict]] = []
    http_client = _make_update_content_client(captured)
    auron = AuronClient(client=http_client)

    result = await auron.update_agent(
        agent_id="35378",
        tenant="noxus",
        name="Agente de prueba",
        description="Descripcion de prueba",
        use_case_owner="owner@example.com",
        agent_owner="agent-owner@example.com",
        provider_version_id="v1.0",
    )

    assert result == {"id": "35378"}
    path, payload = captured[0]
    assert path == "/grc/api/contents/35378"
    assert "primaryParentId" not in payload
    assert payload == {
        "name": "[Agent Noxus] Agente de prueba",
        "description": "Descripcion de prueba",
        "fields": {
            "field": [
                {
                    "id": "3261",
                    "dataType": "STRING_TYPE",
                    "hasChanged": True,
                    "value": "owner@example.com",
                },
                {
                    "id": "3293",
                    "dataType": "STRING_TYPE",
                    "hasChanged": True,
                    "value": "agent-owner@example.com",
                },
                {
                    "id": "3290",
                    "dataType": "STRING_TYPE",
                    "hasChanged": True,
                    "value": "v1.0",
                },
            ]
        },
    }

    await http_client.aclose()


async def test_update_agent_omits_description_when_missing():
    captured: list[tuple[str, dict]] = []
    http_client = _make_update_content_client(captured)
    auron = AuronClient(client=http_client)

    await auron.update_agent(
        agent_id="35378",
        tenant="maisa",
        name="Agente de prueba",
        description=None,
        use_case_owner=None,
        agent_owner="agent-owner@example.com",
        provider_version_id="v1.0",
    )

    _, payload = captured[0]
    assert "description" not in payload
    assert payload["name"] == "[Agent Maisa] Agente de prueba"

    await http_client.aclose()


async def test_update_agent_raises_when_name_missing():
    http_client = httpx.AsyncClient(base_url=settings.auron_base_url)
    auron = AuronClient(client=http_client)

    with pytest.raises(ValueError):
        await auron.update_agent(
            agent_id="35378",
            tenant="maisa",
            name=None,
            description="Descripcion de prueba",
            use_case_owner="owner@example.com",
            agent_owner="agent-owner@example.com",
            provider_version_id="v1.0",
        )

    await http_client.aclose()


async def test_update_agent_raises_when_agent_owner_missing():
    http_client = httpx.AsyncClient(base_url=settings.auron_base_url)
    auron = AuronClient(client=http_client)

    with pytest.raises(ValueError):
        await auron.update_agent(
            agent_id="35378",
            tenant="maisa",
            name="Agente de prueba",
            description="Descripcion de prueba",
            use_case_owner="owner@example.com",
            agent_owner=None,
            provider_version_id="v1.0",
        )

    await http_client.aclose()


async def test_update_agent_raises_when_provider_version_id_missing():
    http_client = httpx.AsyncClient(base_url=settings.auron_base_url)
    auron = AuronClient(client=http_client)

    with pytest.raises(ValueError):
        await auron.update_agent(
            agent_id="35378",
            tenant="maisa",
            name="Agente de prueba",
            description="Descripcion de prueba",
            use_case_owner="owner@example.com",
            agent_owner="agent-owner@example.com",
            provider_version_id=None,
        )

    await http_client.aclose()


def _agent_query_client(calls: list[dict], rows: list[dict]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(
                200, json={"access_token": "tok-123", "expires_in": 3600}
            )
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"rows": rows, "offset": 0, "limit": 50})

    return httpx.AsyncClient(
        base_url=settings.auron_base_url, transport=httpx.MockTransport(handler)
    )


async def test_get_agent_by_worker_id_returns_agent_and_parent_use_case():
    calls: list[dict] = []
    rows = [
        {
            "fields": [
                {"name": "Resource ID", "value": "77001"},
                {"name": "Santander-Fields-Agent:PlatformAgentID", "value": "WM1"},
                {"name": "Resource ID", "value": "40161"},
            ]
        }
    ]
    http_client = _agent_query_client(calls, rows)

    agent = await AuronClient(client=http_client).get_agent_by_worker_id("WM1", "maisa")

    assert agent == {"id": "77001", "primaryParentId": "40161"}
    statement = calls[0]["statement"]
    assert "FROM [AIComponent]" in statement
    assert "JOIN [Register] ON CHILD([AIComponent])" in statement
    assert "[Engagement].[Resource ID] = '11334'" in statement
    assert "[AIComponent].[Santander-Fields-Agent:PlatformAgentID] = 'WM1'" in statement

    await http_client.aclose()


async def test_get_agent_by_worker_id_returns_none_when_not_found():
    calls: list[dict] = []
    http_client = _agent_query_client(calls, rows=[])

    agent = await AuronClient(client=http_client).get_agent_by_worker_id("WM1", "noxus")

    assert agent is None
    assert "[Engagement].[Resource ID] = '15327'" in calls[0]["statement"]

    await http_client.aclose()


async def test_get_use_case_id_by_name_searches_inside_tenant_engagement():
    calls: list[dict] = []
    rows = [{"fields": [{"name": "Resource ID", "value": "50001"}, {"name": "Name", "value": "x"}]}]
    http_client = _agent_query_client(calls, rows)

    use_case_id = await AuronClient(client=http_client).get_use_case_id_by_name(
        "To be regularized - Maisa - HQ - Legal", "maisa"
    )

    assert use_case_id == "50001"
    statement = calls[0]["statement"]
    assert "FROM [Register]" in statement
    assert "[Engagement].[Resource ID] = '11334'" in statement
    assert "[Register].[Name] = 'To be regularized - Maisa - HQ - Legal'" in statement

    await http_client.aclose()


async def test_get_use_case_id_by_name_returns_none_when_not_found():
    calls: list[dict] = []
    http_client = _agent_query_client(calls, rows=[])

    assert await AuronClient(client=http_client).get_use_case_id_by_name("x", "maisa") is None

    await http_client.aclose()


async def test_paginate_query_retries_once_on_401(monkeypatch):
    monkeypatch.setattr(auron_client, "_UNAUTHORIZED_RETRY_DELAY_SECONDS", 0)
    statuses = [401, 200]

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == TOKEN_URL:
            return httpx.Response(
                200, json={"access_token": "tok-123", "expires_in": 3600}
            )
        return httpx.Response(
            statuses.pop(0), json={"rows": [{"fields": []}], "offset": 0, "limit": 50}
        )

    http_client = httpx.AsyncClient(
        base_url=settings.auron_base_url, transport=httpx.MockTransport(handler)
    )
    auron = AuronClient(client=http_client)

    rows = await auron._paginate_query("SELECT 1", await auron._auth_headers())

    assert rows == [{"fields": []}]
    assert statuses == []

    await http_client.aclose()


async def test_get_agent_id_by_worker_id_does_not_require_a_parent():
    calls: list[dict] = []
    rows = [{"fields": [{"name": "Resource ID", "value": "77001"}]}]
    http_client = _agent_query_client(calls, rows)

    agent_id = await AuronClient(client=http_client).get_agent_id_by_worker_id("WM1")

    assert agent_id == "77001"
    statement = calls[0]["statement"]
    assert "JOIN" not in statement
    assert "[AIComponent].[Santander-Fields-Agent:PlatformAgentID] = 'WM1'" in statement

    await http_client.aclose()


async def test_get_use_case_status_reads_enum_status_and_owner():
    calls: list[dict] = []
    rows = [
        {
            "fields": [
                {"name": "Resource ID", "value": "51571"},
                {"name": "Name", "value": "To be regularized - Maisa - HQ - Others"},
                {
                    "name": "Santander Fields:Status",
                    "value": {"id": "1", "name": "Ready for development"},
                },
                {"name": "Santander Fields:Owner", "value": "owner@example.com"},
            ]
        }
    ]
    http_client = _agent_query_client(calls, rows)

    use_case = await AuronClient(client=http_client).get_use_case_status("51571")

    assert use_case == {
        "use_case_id": "51571",
        "name": "To be regularized - Maisa - HQ - Others",
        "status": "Ready for development",
        "owner": "owner@example.com",
    }
    assert "[Register].[Resource ID] = '51571'" in calls[0]["statement"]

    await http_client.aclose()


async def test_get_use_case_status_returns_none_when_not_found():
    calls: list[dict] = []
    http_client = _agent_query_client(calls, rows=[])

    assert await AuronClient(client=http_client).get_use_case_status("1") is None

    await http_client.aclose()
