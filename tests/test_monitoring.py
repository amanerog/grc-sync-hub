import json
import logging
from datetime import datetime, timezone

from sinc_amn.core.monitoring import MonitoringStore


async def test_record_logs_structured_json_with_expected_fields(caplog):
    store = MonitoringStore()
    timestamp = datetime(2026, 7, 27, 10, 30, tzinfo=timezone.utc)

    with caplog.at_level(logging.INFO, logger="sinc_amn.core.monitoring"):
        await store.record(
            worker_id="W-1",
            agent_id="A-1",
            use_case_id="UC-1",
            status="success",
            timestamp=timestamp,
        )

    assert len(caplog.records) == 1
    payload = json.loads(caplog.records[0].getMessage())
    assert payload == {
        "event": "worker_sync_result",
        "worker_id": "W-1",
        "agent_id": "A-1",
        "use_case_id": "UC-1",
        "status": "success",
        "timestamp": timestamp.isoformat(),
    }


async def test_record_logs_error_status():
    store = MonitoringStore()
    timestamp = datetime(2026, 7, 27, 10, 30, tzinfo=timezone.utc)

    # No debe lanzar - registrar un fallo tambien es un caso valido de uso.
    await store.record(
        worker_id="W-1",
        agent_id="",
        use_case_id="UC-1",
        status="error",
        timestamp=timestamp,
    )
