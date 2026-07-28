from datetime import date, datetime, timezone

import httpx
import pytest

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.clients.noxus_client import NoxusClient
from sinc_amn.models.use_case import UseCase


async def test_maisa_client_placeholders_raise_not_implemented():
    client = MaisaClient(client=httpx.AsyncClient())

    with pytest.raises(NotImplementedError):
        await client.get_updated_workers(date(2026, 7, 27))
    with pytest.raises(NotImplementedError):
        await client.create_label(label=None)
    with pytest.raises(NotImplementedError):
        await client.update_label("maisa-1", label=None)

    await client._client.aclose()


async def test_noxus_client_placeholders_raise_not_implemented():
    client = NoxusClient(client=httpx.AsyncClient())
    use_case = UseCase(
        resource_id="RES-1",
        name="Caso 1",
        tenant="noxus",
        updated_at=datetime.now(timezone.utc),
    )

    with pytest.raises(NotImplementedError):
        await client.push_use_case(use_case)
    with pytest.raises(NotImplementedError):
        await client.get_updated_workers(date(2026, 7, 27))

    await client._client.aclose()


async def test_auron_client_agent_placeholders_raise_not_implemented():
    client = AuronClient(client=httpx.AsyncClient())

    with pytest.raises(NotImplementedError):
        await client.get_agent_by_worker_id("W-1")
    with pytest.raises(NotImplementedError):
        await client.create_agent(
            worker_id="W-1", workspace_id="WS-1", use_case_id="UC-1"
        )
    with pytest.raises(NotImplementedError):
        await client.update_agent(
            agent_id="A-1", workspace_id="WS-1", use_case_id="UC-1"
        )

    await client._client.aclose()
