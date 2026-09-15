import json
import logging
from datetime import datetime
from typing import Literal

logger = logging.getLogger(__name__)


class MonitoringStore:
    """Persistencia del resultado de la ingesta en Auron (Flujo 2, paso 6AB).

    Confirmado: el backend es CloudWatch, no una tabla en Postgres - se
    registra como un log estructurado (JSON) via el logger estandar, que
    ya se recoge de stdout del pod en EKS (ver `core/logging.py`). No hace
    falta desde el propio microservicio ningun cliente ni credenciales de
    CloudWatch.
    """

    async def record(
        self,
        worker_id: str,
        agent_id: str,
        use_case_id: str,
        status: Literal["success", "error"],
        timestamp: datetime,
    ) -> None:
        logger.info(
            json.dumps(
                {
                    "event": "worker_sync_result",
                    "worker_id": worker_id,
                    "agent_id": agent_id,
                    "use_case_id": use_case_id,
                    "status": status,
                    "timestamp": timestamp.isoformat(),
                }
            )
        )
