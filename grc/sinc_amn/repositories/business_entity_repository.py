import asyncpg

from sinc_amn.models.workday_member import WorkdayMember


class BusinessEntityRepository:
    """Datos de Workday de cada empleado (`workday_members`), para calcular
    la Business Entity del creador de un agente (ver
    core/business_entity.py). Se carga con scripts/load_reference_data.py.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_member(self, email: str) -> WorkdayMember | None:
        """Datos de Workday por email, sin distinguir mayusculas."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT email, business_unit, position_level_2,
                       functional_group_1, country
                FROM workday_members
                WHERE email = lower($1)
                """,
                email.strip(),
            )
        return WorkdayMember(**dict(row)) if row else None
