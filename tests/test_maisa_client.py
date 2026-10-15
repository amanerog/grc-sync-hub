from unittest.mock import MagicMock

from sinc_amn.clients.maisa_client import MaisaClient


def test_constructor_accepts_mongo_client_override():
    fake_mongo_client = MagicMock()

    client = MaisaClient(mongo_client=fake_mongo_client)

    assert client._mongo_client is fake_mongo_client
