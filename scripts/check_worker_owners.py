"""Muestra, para los workers de Maisa de un dia, su creador, si esta en
Workday y a que Business Entity cae (Flujo 2, caso de uso generico).

Solo lectura. Sirve para entender por que un agente acaba en un generico
concreto (p.ej. "HQ - Others" porque el creador no esta en Workday):

    kubectl exec -n <ns> <pod> -- python scripts/check_worker_owners.py --day 2026-10-23

Sin --day revisa D-1, igual que el CronJob. Con --worker revisa esos
worker_manager concretos, sea cual sea su fecha (la BBDD de DEV cambia y
un dia que tenia workers puede dejar de tenerlos):

    kubectl exec -n <ns> <pod> -- python scripts/check_worker_owners.py --worker 6a7acef1da610e0e51538f78
 Usa la misma BBDD que el
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


def _print_worker(worker_id, name, label, owner, member) -> None:
    print(f"\n{worker_id}  {name}")
    if label is not None:
        print(f"  label:   {label!r}")
    print(f"  creador: {owner!r}")
    if member is None:
        print("  NO esta en Workday")
    else:
        print(
            f"  Workday: BU={member.business_unit!r} "
            f"PL2={member.position_level_2!r} "
            f"FG1={member.functional_group_1!r}"
        )
    print(f"  BE:      {business_entity_for(member)}")


async def _owners_by_id(maisa: MaisaClient, worker_ids: list[str]) -> list[tuple]:
    """(worker_id, nombre, email del creador) leidos directamente de
    `worker_manager`/`user`, sin los filtros de Flujo 2."""
    db = maisa._db
    managers = await db.worker_manager.find(
        {"worker_manager": {"$in": worker_ids}}
    ).to_list(None)
    user_ids = [m.get("worker_manager_user") for m in managers]
    emails = {
        user["user_id"]: user.get("email")
        async for user in db.user.find({"user_id": {"$in": user_ids}})
    }
    found = {m["worker_manager"] for m in managers}
    for missing in sorted(set(worker_ids) - found):
        print(f"\n{missing}  NO existe en worker_manager")
    return [
        (
            m["worker_manager"],
            m.get("worker_manager_name"),
            emails.get(m.get("worker_manager_user")),
        )
        for m in managers
    ]


async def _check(day: date, worker_ids: list[str]) -> None:
    pool = await asyncpg.create_pool(os.environ["SINC_AMN_INTERMEDIATE_DB_DSN"])
    try:
        repo = BusinessEntityRepository(pool)
        async with pool.acquire() as conn:
            members = await conn.fetchval("SELECT count(*) FROM workday_members")
        maisa = MaisaClient()

        if worker_ids:
            print(f"{members} filas en workday_members")
            for worker_id, name, owner in await _owners_by_id(maisa, worker_ids):
                member = await repo.get_member(owner) if owner else None
                _print_worker(worker_id, name, None, owner, member)
            return

        print(f"dia {day}, {members} filas en workday_members")
        workers = await maisa.get_updated_workers(day)
        for worker in workers:
            member = (
                await repo.get_member(worker.agent_owner)
                if worker.agent_owner
                else None
            )
            _print_worker(
                worker.worker_id,
                worker.agent_name,
                worker.use_case_id,
                worker.agent_owner,
                member,
            )
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
    parser.add_argument(
        "--worker",
        action="append",
        default=[],
        help="id de worker_manager (repetible); si se pasa, se ignora --day",
    )
    args = parser.parse_args()
    asyncio.run(_check(args.day, args.worker))


if __name__ == "__main__":
    main()
