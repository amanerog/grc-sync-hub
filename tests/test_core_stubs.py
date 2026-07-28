from datetime import datetime, timezone

import pytest

from sinc_amn.core.checkpoint import CheckpointStore
from sinc_amn.core.monitoring import MonitoringStore
from sinc_amn.core.notifications import AdminNotifier


async def test_checkpoint_store_is_not_implemented():
    store = CheckpointStore()

    with pytest.raises(NotImplementedError):
        await store.get_last_checkpoint()
    with pytest.raises(NotImplementedError):
        await store.set_last_checkpoint(datetime.now(timezone.utc))


async def test_monitoring_store_is_not_implemented():
    store = MonitoringStore()

    with pytest.raises(NotImplementedError):
        await store.record(
            worker_id="W-1",
            agent_id="A-1",
            use_case_id="UC-1",
            status="success",
            timestamp=datetime.now(timezone.utc),
        )


async def test_admin_notifier_is_not_implemented():
    notifier = AdminNotifier()

    with pytest.raises(NotImplementedError):
        await notifier.notify_pending_regularization(
            workspace_id="WS-1", worker_id="W-1"
        )
