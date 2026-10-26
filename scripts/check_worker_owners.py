"""Muestra, para los workers de Maisa de un dia, su creador, si esta en
Workday y a que Business Entity cae (Flujo 2, caso de uso generico).

Solo lectura. Sirve para entender por que un agente acaba en un generico
concreto (p.ej. "HQ - Others" porque el creador no esta en Workday):

    kubectl exec -n <ns> <pod> -- python scripts/check_worker_owners.py --day 2026-10-23

Sin --day revisa D-1, igual que el CronJob. Usa la misma BBDD que el
servicio (SINC_AMN_INTERMEDIATE_DB_DSN) y la misma conexion a Maisa.
"""

import argparse
import asyncio
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grc"))

from sinc_amn.clients.maisa_client import MaisaClient  # noqa: E402
from sinc_amn.core.business_entity import business_entity_for  # noqa: E402
from sinc_amn.repositories.business_entity_repository import (  # noqa: E402
    BusinessEntityRepository,
)


async def _check(day: date) -> None:
    pool = await asyncpg.create_pool(os.environ["SINC_AMN_INTERMEDIATE_DB_DSN"])
    try:
        repo = BusinessEntityRepository(pool)
        async with pool.acquire() as conn:
            members = await conn.fetchval("SELECT count(*) FROM workday_members")
        print(f"dia {day}, {members} filas en workday_members")

        workers = await MaisaClient().get_updated_workers(day)
        for worker in workers:
            member = (
                await repo.get_member(worker.agent_owner)
                if worker.agent_owner
                else None
            )
            print(f"\n{worker.worker_id}  {worker.agent_name}")
            print(f"  label:   {worker.use_case_id!r}")
            print(f"  creador: {worker.agent_owner!r}")
            if member is None:
                print("  NO esta en Workday")
            else:
                print(
                    f"  Workday: BU={member.business_unit!r} "
                    f"PL2={member.position_level_2!r} "
                    f"FG1={member.functional_group_1!r}"
                )
            print(f"  BE:      {business_entity_for(member)}")
        print(f"\n{len(workers)} workers")
    finally:
        await pool.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--day",
        type=date.fromisoformat,
        default=date.today() - timedelta(days=1),
        help="YYYY-MM-DD (por defecto D-1)",
    )
    asyncio.run(_check(parser.parse_args().day))


if __name__ == "__main__":
    main()
