from datetime import datetime, timezone

import asyncpg


class UseCaseSyncFailureRepository:
    """Tracking de fallos aislados de Flujo 1 (Postgres/RDS, `use_case_sync_failures`).

    Permite reintentar por Resource ID explicito en vez de depender de que
    el item siga cayendo dentro de la ventana `settings.auron_use_cases_since`
    (ver `UseCaseSyncService` y `AuronClient.get_use_cases_by_resource_ids`).
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def record_failure(self, resource_id: str, tenant: str, error: str) -> None:
        """Registra un fallo: nuevo incidente si no habia uno abierto, o
        incrementa `attempts` si ya estaba pendiente de una ejecucion previa.
        """
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO use_case_sync_failures
                    (resource_id, tenant, error, attempts, first_failed_at,
                     last_attempt_at, resolved_at)
                VALUES ($1, $2, $3, 1, $4, $4, NULL)
                ON CONFLICT (resource_id) DO UPDATE SET
                    tenant = EXCLUDED.tenant,
                    error = EXCLUDED.error,
                    attempts = CASE
                        WHEN use_case_sync_failures.resolved_at IS NULL
                            THEN use_case_sync_failures.attempts + 1
                        ELSE 1
                    END,
                    first_failed_at = CASE
                        WHEN use_case_sync_failures.resolved_at IS NULL
                            THEN use_case_sync_failures.first_failed_at
                        ELSE EXCLUDED.first_failed_at
                    END,
                    last_attempt_at = EXCLUDED.last_attempt_at,
                    resolved_at = NULL
                """,
                resource_id,
                tenant,
                error,
                now,
            )

    async def mark_resolved(self, resource_id: str) -> None:
        """No-op si `resource_id` no tenia ningun fallo registrado."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE use_case_sync_failures
                SET resolved_at = $2
                WHERE resource_id = $1
                """,
                resource_id,
                datetime.now(timezone.utc),
            )

    async def get_pending(self) -> list[dict]:
        """`resource_id`/`tenant` de fallos aun sin resolver."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT resource_id, tenant
                FROM use_case_sync_failures
                WHERE resolved_at IS NULL
                """
            )
        return [dict(row) for row in rows]
