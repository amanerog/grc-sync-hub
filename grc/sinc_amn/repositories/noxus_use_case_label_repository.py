from datetime import datetime, timezone
from uuid import UUID, uuid4

import asyncpg

from sinc_amn.models.noxus_use_case_label import NoxusUseCaseLabel
from sinc_amn.models.use_case import UseCase
from sinc_amn.models.use_case_label import LabelStatus


class NoxusUseCaseLabelRepository:
    """Tabla intermedia (Postgres/RDS) que vincula OpenPages con Noxus.

    Mismo diseño y ciclo de vida que `UseCaseLabelRepository` (Maisa) - la
    escriben dos piezas distintas (ver ARCHITECTURE.md):
    - "Funcionalidad 1 - Noxus" (OpenPages -> tabla intermedia):
      upsert_from_use_case, deja status 'new'/'modified'.
    - "Funcionalidad * - Noxus" (tabla intermedia -> Noxus):
      get_pending_for_noxus / mark_synced, consume 'new'/'modified' y deja
      'synced'.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def upsert_from_use_case(
        self,
        use_case: UseCase,
        organization_id: str,
        workspace_id: str | None = None,
    ) -> NoxusUseCaseLabel:
        """Insert si el resource_id de OpenPages es nuevo; update si ya existia.

        worker_count no se toca en el update (mismo criterio que Maisa,
        confirmado). `workspace_id`: `UseCase` (el dato de origen,
        OpenPages) no lo trae, asi que en el INSERT arranca en lo que venga
        (probablemente `None` en la ingesta desde Flujo 1 - ver TODO en
        `models/noxus_use_case_label.py`); en el UPDATE solo se sobreescribe
        si se pasa un valor no nulo, para no pisar uno ya rellenado por otro
        paso.
        """
        name_lower = use_case.name.strip().lower()
        now = datetime.now(timezone.utc)

        async with self._pool.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT * FROM noxus_use_case_labels
                WHERE organization_id = $1 AND source_resource_id = $2
                """,
                organization_id,
                use_case.resource_id,
            )

            if existing is None:
                row = await conn.fetchrow(
                    """
                    INSERT INTO noxus_use_case_labels
                        (id, source_resource_id, name, name_lower, entity, owner,
                         workspace_id, organization_id, worker_count, status,
                         created_at, updated_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 0, 'new', $9, $9)
                    RETURNING *
                    """,
                    uuid4(),
                    use_case.resource_id,
                    use_case.name,
                    name_lower,
                    use_case.entity,
                    use_case.owner,
                    workspace_id,
                    organization_id,
                    now,
                )
            else:
                row = await conn.fetchrow(
                    """
                    UPDATE noxus_use_case_labels
                    SET name = $1, name_lower = $2, entity = $3, owner = $4,
                        workspace_id = COALESCE($5, workspace_id),
                        status = 'modified', updated_at = $6
                    WHERE id = $7
                    RETURNING *
                    """,
                    use_case.name,
                    name_lower,
                    use_case.entity,
                    use_case.owner,
                    workspace_id,
                    now,
                    existing["id"],
                )

        return NoxusUseCaseLabel(**dict(row))

    async def get_by_resource_id(
        self, resource_id: str, organization_id: str
    ) -> NoxusUseCaseLabel | None:
        """Busca un registro por su Resource ID de origen.

        Usado por Flujo 2 (WorkerSyncService) para leer el owner del Use
        Case al crear/actualizar un Agent, sin GET adicional a OpenPages -
        equivalente Noxus de `UseCaseLabelRepository.get_by_resource_id`.
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT * FROM noxus_use_case_labels
                WHERE organization_id = $1 AND source_resource_id = $2
                """,
                organization_id,
                resource_id,
            )
        return NoxusUseCaseLabel(**dict(row)) if row else None

    async def get_pending_for_noxus(self, organization_id: str) -> list[NoxusUseCaseLabel]:
        """Registros nuevos/modificados desde el ultimo sync a Noxus."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM noxus_use_case_labels
                WHERE organization_id = $1 AND status IN ('new', 'modified')
                ORDER BY updated_at
                """,
                organization_id,
            )
        return [NoxusUseCaseLabel(**dict(row)) for row in rows]

    async def mark_synced(
        self, label_id: UUID, noxus_label_id: str, expected_status: LabelStatus
    ) -> None:
        """Marca un registro como sincronizado con Noxus.

        Solo transiciona si el status no ha cambiado desde que se leyo como
        pendiente (expected_status), mismo criterio optimista que Maisa.
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE noxus_use_case_labels
                SET status = 'synced', noxus_label_id = $1, updated_at = $2
                WHERE id = $3 AND status = $4
                """,
                noxus_label_id,
                datetime.now(timezone.utc),
                label_id,
                expected_status,
            )
