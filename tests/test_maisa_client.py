import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.config import settings
from sinc_amn.models.use_case_label import UseCaseLabel


def _label(**overrides) -> UseCaseLabel:
    now = datetime.now(timezone.utc)
    data = dict(
        id=uuid4(),
        source_resource_id="RES-1",
        name="Caso 1",
        name_lower="caso 1",
        organization_id="org-1",
        worker_count=0,
        status="new",
        created_at=now,
        updated_at=now,
    )
    data.update(overrides)
    return UseCaseLabel(**data)


async def test_get_access_token_is_not_implemented():
    client = MaisaClient(client=httpx.AsyncClient())

    with pytest.raises(NotImplementedError):
        await client._get_access_token()

    await client._client.aclose()


def _make_labels_client(captured: list[dict]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/organizations/org-1/labels"
        assert request.headers["Authorization"] == "Bearer fake-sts-token"
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "maisa-generated-id", "name": "Caso 1"})

    return httpx.AsyncClient(
        base_url=settings.maisa_base_url,
        transport=httpx.MockTransport(handler),
    )


async def test_create_label_posts_to_organization_scoped_endpoint(monkeypatch):
    captured: list[dict] = []
    http_client = _make_labels_client(captured)
    client = MaisaClient(client=http_client)
    monkeypatch.setattr(
        client, "_get_access_token", AsyncMock(return_value="fake-sts-token")
    )
    label = _label()

    maisa_label_id = await client.create_label(label)

    assert maisa_label_id == "maisa-generated-id"
    # organization_id va en la URL (path del handler ya lo comprueba), no en
    # el body - el body es minimo, solo "name".
    assert captured == [{"name": "Caso 1"}]

    await http_client.aclose()


async def test_create_label_raises_on_http_error(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    http_client = httpx.AsyncClient(
        base_url=settings.maisa_base_url,
        transport=httpx.MockTransport(handler),
    )
    client = MaisaClient(client=http_client)
    monkeypatch.setattr(
        client, "_get_access_token", AsyncMock(return_value="fake-sts-token")
    )

    with pytest.raises(httpx.HTTPStatusError):
        await client.create_label(_label())

    await http_client.aclose()


async def test_create_label_propagates_not_implemented_from_token_fetch():
    # Sin mockear _get_access_token: create_label debe fallar ahi mismo,
    # sin llegar a hacer ninguna llamada HTTP real a Maisa.
    http_client = httpx.AsyncClient(base_url=settings.maisa_base_url)
    client = MaisaClient(client=http_client)

    with pytest.raises(NotImplementedError):
        await client.create_label(_label())

    await http_client.aclose()
