from unittest.mock import AsyncMock

from sinc_amn.services.checkpoint_service import CheckpointService


def _service(
    worker_manager_id="wm-1",
    agent=None,
    agent_id=None,
    use_case=None,
):
    auron = AsyncMock()
    auron.get_agent_by_worker_id.return_value = agent
    auron.get_agent_id_by_worker_id.return_value = agent_id
    auron.get_use_case_status.return_value = use_case
    maisa = AsyncMock()
    maisa.get_worker_manager_id.return_value = worker_manager_id
    return CheckpointService(auron=auron, maisa=maisa), auron


async def test_get_agent_returns_none_for_unknown_version():
    service, auron = _service(worker_manager_id=None)

    assert await service.get_agent("v-404") is None
    auron.get_agent_by_worker_id.assert_not_called()


async def test_get_agent_without_agent_in_openpages():
    service, auron = _service()

    result = await service.get_agent("v-1")

    assert result == {
        "worker_id": "v-1",
        "worker_manager_id": "wm-1",
        "agent_id": None,
        "use_case_id": None,
        "use_case_name": None,
        "use_case_status": None,
        "is_generic_use_case": False,
    }
    auron.get_agent_by_worker_id.assert_awaited_once_with("wm-1", "maisa")
    auron.get_agent_id_by_worker_id.assert_awaited_once_with("wm-1")


async def test_get_agent_that_exists_without_use_case():
    service, _ = _service(agent_id="54161")

    result = await service.get_agent("v-1")

    assert result["agent_id"] == "54161"
    assert result["use_case_id"] is None


async def test_get_agent_in_generic_use_case():
    service, auron = _service(
        agent={"id": "54161", "primaryParentId": "51571"},
        use_case={
            "use_case_id": "51571",
            "name": "To be regularized - Maisa - HQ - Others",
            "status": "Draft",
            "owner": None,
        },
    )

    result = await service.get_agent("v-1")

    assert result["agent_id"] == "54161"
    assert result["use_case_id"] == "51571"
    assert result["use_case_name"] == "To be regularized - Maisa - HQ - Others"
    assert result["use_case_status"] == "Draft"
    assert result["is_generic_use_case"] is True
    auron.get_agent_id_by_worker_id.assert_not_called()


async def test_get_agent_in_regular_use_case():
    service, _ = _service(
        agent={"id": "47378", "primaryParentId": "11281"},
        use_case={
            "use_case_id": "11281",
            "name": "Prueba sinc-amn",
            "status": "Ready for development",
            "owner": "owner@example.com",
        },
    )

    result = await service.get_agent("v-1")

    assert result["is_generic_use_case"] is False
    assert result["use_case_status"] == "Ready for development"


async def test_get_use_case_passes_through():
    use_case = {"use_case_id": "1", "name": "x", "status": "s", "owner": None}
    service, auron = _service(use_case=use_case)

    assert await service.get_use_case("1") == use_case
    auron.get_use_case_status.assert_awaited_once_with("1")
