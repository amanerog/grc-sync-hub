import json
from datetime import datetime, timezone
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


def _make_labels_client(captured: list[dict]) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/organizations/org-1/labels"
        assert request.headers["Authorization"] == f"Bearer {settings.maisa_api_key}"
        captured.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "maisa-generated-id", "name": "Caso 1"})

    return httpx.AsyncClient(
        base_url=settings.maisa_base_url,
        headers={"Authorization": f"Bearer {settings.maisa_api_key}"},
        transport=httpx.MockTransport(handler),
    )


async def test_create_label_posts_to_organization_scoped_endpoint():
    captured: list[dict] = []
    http_client = _make_labels_client(captured)
    client = MaisaClient(client=http_client)
    label = _label()

    maisa_label_id = await client.create_label(label)

    assert maisa_label_id == "maisa-generated-id"
    # organization_id va en la URL (path del handler ya lo comprueba), no en
    # el body - el body es minimo, solo "name".
    assert captured == [{"name": "Caso 1"}]

    await http_client.aclose()


async def test_create_label_raises_on_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    http_client = httpx.AsyncClient(
        base_url=settings.maisa_base_url,
        headers={"Authorization": f"Bearer {settings.maisa_api_key}"},
        transport=httpx.MockTransport(handler),
    )
    client = MaisaClient(client=http_client)

    with pytest.raises(httpx.HTTPStatusError):
        await client.create_label(_label())

    await http_client.aclose()
