from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

import sinc_amn.main as main_module
from sinc_amn.main import app


def test_lifespan_starts_and_closes_pool(monkeypatch):
    create_pool_mock = AsyncMock()
    close_pool_mock = AsyncMock()
    monkeypatch.setattr(main_module, "create_pool", create_pool_mock)
    monkeypatch.setattr(main_module, "close_pool", close_pool_mock)

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    create_pool_mock.assert_awaited_once()
    close_pool_mock.assert_awaited_once()
