from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock

from sinc_amn.clients.maisa_client import MaisaClient, _use_case_id_from_labels


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


def _matches(doc: dict, query: dict) -> bool:
    for key, cond in query.items():
        value = doc.get(key)
        if isinstance(cond, dict):
            for op, arg in cond.items():
                if op == "$in" and value not in arg:
                    return False
                if op == "$ne" and value == arg:
                    return False
                if op == "$gte" and not (value is not None and value >= arg):
                    return False
                if op == "$lt" and not (value is not None and value < arg):
                    return False
        elif value != cond:
            return False
    return True


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length):
        return list(self._docs)

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class _FakeCollection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query):
        return _FakeCursor([d for d in self._docs if _matches(d, query)])

    async def distinct(self, field, query):
        return sorted({d[field] for d in self._docs if _matches(d, query)})


def _fake_mongo(**collections):
    db = MagicMock()
    for name, docs in collections.items():
        setattr(db, name, _FakeCollection(docs))
    mongo = MagicMock()
    mongo.__getitem__.return_value = db
    return mongo


def _version(manager, version, status, updated, **extra):
    return {
        "worker_manager": manager,
        "worker_id": f"{manager}-v{version}",
        "worker_version": version,
        "worker_status": status,
        "maisa_updated_ts": updated,
        "is_deleted": False,
        "entity": "Spain",
        "environment": "PRE",
        **extra,
    }


def _manager(manager, **extra):
    return {
        "worker_manager": manager,
        "worker_manager_name": f"Agente {manager}",
        "worker_manager_user": "U1",
        "workspace": "WS1",
        "label_ids": ["L1"],
        "is_deleted": False,
        "is_user_excluded": False,
        "entity": "Spain",
        "environment": "PRE",
        **extra,
    }


async def test_get_updated_workers_maps_worker_manager_to_worker():
    day = date(2026, 10, 18)
    mongo = _fake_mongo(
        worker=[
            _version("WM1", 1, "DRAFT", datetime(2026, 9, 1)),
            _version("WM1", 2, "DEPLOYED", datetime(2026, 9, 2)),
            # El cambio de D-1 es en un draft: el agente se sincroniza igual,
            # con la version DEPLOYED mas alta.
            _version("WM1", 3, "DRAFT", datetime(2026, 10, 18, 9, 30)),
        ],
        worker_manager=[_manager("WM1")],
        label=[{"label_id": "L1", "name": "559_Riesgos-Admision", "is_deleted": False}],
        user=[{"user_id": "U1", "email": "owner@example.com"}],
    )

    workers = await MaisaClient(mongo_client=mongo).get_updated_workers(day)

    assert len(workers) == 1
    w = workers[0]
    assert w.worker_id == "WM1"
    assert w.workspace_id == "WS1"
    assert w.tenant == "maisa"
    assert w.use_case_id == "559"
    assert w.updated_at == day
    assert w.agent_name == "Agente WM1"
    assert w.agent_owner == "owner@example.com"
    assert w.provider_version_id == "2"


async def test_get_updated_workers_filters_out_non_matching_agents():
    day = date(2026, 10, 18)
    changed = datetime(2026, 10, 18, 12, 0)
    mongo = _fake_mongo(
        worker=[
            # Sin version DEPLOYED.
            _version("WM-draft", 1, "DRAFT", changed),
            # Otro entorno.
            _version("WM-pro", 1, "DEPLOYED", changed, environment="PRO"),
            # Cambio fuera de D-1.
            _version("WM-old", 1, "DEPLOYED", datetime(2026, 10, 17, 23, 59)),
            # Agente borrado / excluido.
            _version("WM-deleted", 1, "DEPLOYED", changed),
            _version("WM-excluded", 1, "DEPLOYED", changed),
        ],
        worker_manager=[
            _manager("WM-draft"),
            _manager("WM-pro", environment="PRO"),
            _manager("WM-old"),
            _manager("WM-deleted", is_deleted=True),
            _manager("WM-excluded", is_user_excluded=True),
        ],
        label=[],
        user=[],
    )

    assert await MaisaClient(mongo_client=mongo).get_updated_workers(day) == []


def test_use_case_id_from_labels_uses_resource_id_prefix():
    assert _use_case_id_from_labels("WM1", ["559_Riesgos"]) == "559"
    assert _use_case_id_from_labels("WM1", ["l1 - compliance", None]) is None
    assert _use_case_id_from_labels("WM1", []) is None
    # Varios casos de uso distintos: el primero.
    assert _use_case_id_from_labels("WM1", ["x", "12_A", "34_B", "12_C"]) == "12"
