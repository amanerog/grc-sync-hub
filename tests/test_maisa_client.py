from unittest.mock import AsyncMock, MagicMock

from sinc_amn.clients.maisa_client import MaisaClient


def test_constructor_accepts_mongo_client_override():
    fake_mongo_client = MagicMock()

    client = MaisaClient(mongo_client=fake_mongo_client)

    assert client._mongo_client is fake_mongo_client


async def test_check_connection_pings_and_lists_collections():
    fake_mongo_client = MagicMock()
    fake_mongo_client.admin.command = AsyncMock(return_value={"ok": 1})
    fake_db = MagicMock()
    fake_db.list_collection_names = AsyncMock(return_value=["worker", "label"])
    fake_mongo_client.__getitem__.return_value = fake_db

    result = await MaisaClient(mongo_client=fake_mongo_client).check_connection()

    fake_mongo_client.admin.command.assert_awaited_once_with("ping")
    fake_mongo_client.__getitem__.assert_called_once_with("gpp_maisa_metrics")
    assert result == {
        "database": "gpp_maisa_metrics",
        "collections": ["label", "worker"],
    }
