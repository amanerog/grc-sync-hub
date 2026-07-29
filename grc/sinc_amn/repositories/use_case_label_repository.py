from datetime import datetime, timezone
from uuid import UUID, uuid4

import asyncpg

from sinc_amn.models.use_case import UseCase
from sinc_amn.models.use_case_label import LabelStatus, UseCaseLabel


class UseCaseLabelRepository:
    """Tabla intermedia (Postgres/RDS) que vincula OpenPages con Maisa.

    La escriben dos piezas distintas (ver ARCHITECTURE.md):
    - "Funcionalidad 1" (OpenPages -> tabla intermedia): upsert_from_use_case,
      deja status 'new'/'modified'.
    - "Funcionalidad *" (tabla intermedia -> Maisa DocumentDB):
      get_pending_for_maisa / mark_synced, consume 'new'/'modified' y deja
      'synced'.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert_from_use_case(
        self, use_case: UseCase, organization_id: str
    ) -> UseCaseLabel:
        """Insert si el resource_id de OpenPages es nuevo; update si ya existia.

        worker_count no se toca en el update: lo mantiene Maisa (asignacion y
        desasignacion de workers), no la ingesta desde OpenPages.
        """
        name_lower = use_case.name.strip().lower()
        now = datetime.now(timezone.utc)

        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT * FROM maisa_use_case_labels
                WHERE organization_id = $1 AND source_resource_id = $2
                """,
                organization_id,
                use_case.resource_id,
            )

            if existing is None:
                row = await conn.fetchrow(
                    """
                    INSERT INTO maisa_use_case_labels
                        (id, source_resource_id, name, name_lower, entity,
                         organization_id, worker_count, status, created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, 0, 'new', $7, $7)
                    RETURNING *
                    """,
                    uuid4(),
                    use_case.resource_id,
                    use_case.name,
                    name_lower,
                    use_case.entity,
                    organization_id,
                    now,
                )
            else:
                row = await conn.fetchrow(
                    """
                    UPDATE maisa_use_case_labels
                    SET name = $1, name_lower = $2, entity = $3, status = 'modified',
                        updated_at = $4
                    WHERE id = $5
                    RETURNING *
                    """,
                    use_case.name,
                    name_lower,
                    use_case.entity,
                    now,
                    existing["id"],
                )

        return UseCaseLabel(**dict(row))

    async def get_pending_for_maisa(self, organization_id: str) -> list[UseCaseLabel]:
        """Registros nuevos/modificados desde el ultimo sync a Maisa."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM maisa_use_case_labels
                WHERE organization_id = $1 AND status IN ('new', 'modified')
                ORDER BY updated_at
                """,
                organization_id,
            )
        return [UseCaseLabel(**dict(row)) for row in rows]

    async def mark_synced(
        self, label_id: UUID, maisa_label_id: str, expected_status: LabelStatus
    ) -> None:
        """Marca un registro como sincronizado con Maisa.

        Solo transiciona si el status no ha cambiado desde que se leyo como
        pendiente (expected_status), para no pisar un 'modified' mas reciente
        que haya escrito "Funcionalidad 1" mientras se procesaba el push.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE maisa_use_case_labels
                SET status = 'synced', maisa_label_id = $1, updated_at = $2
                WHERE id = $3 AND status = $4
                """,
                maisa_label_id,
                datetime.now(timezone.utc),
                label_id,
                expected_status,
            )
