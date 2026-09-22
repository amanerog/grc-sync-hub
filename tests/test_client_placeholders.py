from datetime import date

import httpx
import pytest

from sinc_amn.clients.auron_client import AuronClient
from sinc_amn.clients.maisa_client import MaisaClient
from sinc_amn.clients.noxus_client import NoxusClient


async def test_maisa_client_placeholders_raise_not_implemented():
    client = MaisaClient(client=httpx.AsyncClient())

    with pytest.raises(NotImplementedError):
        await client.get_updated_workers(date(2026, 7, 27))
    with pytest.raises(NotImplementedError):
        await client.update_label("maisa-1", label=None)

    await client._client.aclose()


async def test_noxus_client_placeholders_raise_not_implemented():
    client = NoxusClient(client=httpx.AsyncClient())

    with pytest.raises(NotImplementedError):
        await client.get_updated_workers(date(2026, 7, 27))
    with pytest.raises(NotImplementedError):
        await client.create_label(label=None)
    with pytest.raises(NotImplementedError):
        await client.update_label("noxus-1", label=None)

    await client._client.aclose()


async def test_auron_client_agent_placeholders_raise_not_implemented():
    client = AuronClient(client=httpx.AsyncClient())

    with pytest.raises(NotImplementedError):
        await client.get_agent_by_worker_id("W-1")

    await client._client.aclose()
