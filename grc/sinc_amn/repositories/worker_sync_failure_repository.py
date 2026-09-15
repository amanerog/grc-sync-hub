from datetime import datetime, timezone

import asyncpg

from sinc_amn.models.worker import Worker


class WorkerSyncFailureRepository:
    """Tracking de fallos aislados de Flujo 2 (Postgres/RDS, `worker_sync_failures`).

    A diferencia de Flujo 1 (`UseCaseSyncFailureRepository`), aqui no hay
    forma confirmada de re-pedir un worker por ID a Maisa/Noxus (su
    contrato REST solo ofrece `get_updated_workers(dia)`, no un lookup por
    ID) - por eso se guarda una foto completa del `Worker` en el momento
    del fallo, y el reintento reconstruye el `Worker` directamente desde
    esta tabla sin volver a llamar a Maisa/Noxus. Riesgo aceptado: si el
    dato cambio en origen tras el fallo, el reintento usa la version
    vieja. Confirmado que esta tabla no guarda los exitos (esos se auditan
    aparte via CloudWatch).
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record_failure(self, worker: Worker, error: str) -> None:
        """Registra un fallo: nuevo incidente si no habia uno abierto, o
        incrementa `attempts` si ya estaba pendiente de una ejecucion
        previa. La foto del Worker se actualiza siempre al valor mas
        reciente, aunque ya hubiera un incidente abierto.
        """
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO worker_sync_failures
                    (worker_id, workspace_id, tenant, use_case_id,
                     worker_updated_at, agent_name, agent_description,
                     agent_owner, provider_version_id, error, attempts,
                     first_failed_at, last_attempt_at, resolved_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 1, $11, $11, NULL)
                ON CONFLICT (worker_id) DO UPDATE SET
                    workspace_id = EXCLUDED.workspace_id,
                    tenant = EXCLUDED.tenant,
                    use_case_id = EXCLUDED.use_case_id,
                    worker_updated_at = EXCLUDED.worker_updated_at,
                    agent_name = EXCLUDED.agent_name,
                    agent_description = EXCLUDED.agent_description,
                    agent_owner = EXCLUDED.agent_owner,
                    provider_version_id = EXCLUDED.provider_version_id,
                    error = EXCLUDED.error,
                    attempts = CASE
                        WHEN worker_sync_failures.resolved_at IS NULL
                            THEN worker_sync_failures.attempts + 1
                        ELSE 1
                    END,
                    first_failed_at = CASE
                        WHEN worker_sync_failures.resolved_at IS NULL
                            THEN worker_sync_failures.first_failed_at
                        ELSE EXCLUDED.first_failed_at
                    END,
                    last_attempt_at = EXCLUDED.last_attempt_at,
                    resolved_at = NULL
                """,
                worker.worker_id,
                worker.workspace_id,
                worker.tenant,
                worker.use_case_id,
                worker.updated_at,
                worker.agent_name,
                worker.agent_description,
                worker.agent_owner,
                worker.provider_version_id,
                error,
                now,
            )

    async def mark_resolved(self, worker_id: str) -> None:
        """No-op si `worker_id` no tenia ningun fallo registrado."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE worker_sync_failures
                SET resolved_at = $2
                WHERE worker_id = $1
                """,
                worker_id,
                datetime.now(timezone.utc),
            )

    async def get_pending(self) -> list[Worker]:
        """Reconstruye los `Worker` aun pendientes de reintento a partir de
        su ultima foto guardada, sin volver a llamar a Maisa/Noxus.
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT worker_id, workspace_id, tenant, use_case_id,
                       worker_updated_at, agent_name, agent_description,
                       agent_owner, provider_version_id
                FROM worker_sync_failures
                WHERE resolved_at IS NULL
                """
            )
        return [
            Worker(
                worker_id=row["worker_id"],
                workspace_id=row["workspace_id"],
                tenant=row["tenant"],
                use_case_id=row["use_case_id"],
                updated_at=row["worker_updated_at"],
                agent_name=row["agent_name"],
                agent_description=row["agent_description"],
                agent_owner=row["agent_owner"],
                provider_version_id=row["provider_version_id"],
            )
            for row in rows
        ]
