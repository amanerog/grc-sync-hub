from unittest.mock import AsyncMock

import pytest

from sinc_amn.db import pool as pool_module


@pytest.fixture(autouse=True)
def _reset_pool(monkeypatch):
    monkeypatch.setattr(pool_module, "_pool", None)
    yield
    monkeypatch.setattr(pool_module, "_pool", None)


async def test_get_pool_raises_when_not_initialized():
    with pytest.raises(RuntimeError):
        pool_module.get_pool()


async def test_create_pool_sets_and_returns_pool(monkeypatch):
    fake_pool = AsyncMock()
    create_pool_mock = AsyncMock(return_value=fake_pool)
    monkeypatch.setattr(pool_module.asyncpg, "create_pool", create_pool_mock)

    result = await pool_module.create_pool()

    assert result is fake_pool
    assert pool_module.get_pool() is fake_pool
    create_pool_mock.assert_awaited_once_with(
        dsn=pool_module.settings.intermediate_db_dsn, min_size=0
    )


async def test_close_pool_closes_and_clears(monkeypatch):
    fake_pool = AsyncMock()
    monkeypatch.setattr(pool_module, "_pool", fake_pool)

    await pool_module.close_pool()

    fake_pool.close.assert_awaited_once()
    with pytest.raises(RuntimeError):
        pool_module.get_pool()


async def test_close_pool_noop_when_not_initialized():
    await pool_module.close_pool()
