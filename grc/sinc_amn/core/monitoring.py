from datetime import datetime
from typing import Literal


class MonitoringStore:
    """Persistencia del resultado de la ingesta en Auron (Flujo 2, paso 6AB).

    Backend y payload exacto pendientes de cerrar (ver ARCHITECTURE.md). De
    minimos: worker_id, agent_id, use_case_id, estado y timestamp.
    """

    async def record(
        self,
        worker_id: str,
        agent_id: str,
        use_case_id: str,
        status: Literal["success", "error"],
        timestamp: datetime,
    ) -> None:
        raise NotImplementedError
