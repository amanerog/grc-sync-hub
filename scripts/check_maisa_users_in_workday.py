"""Cruza los usuarios de Maisa (coleccion `user` de la DocumentDB) con
workday_members: cuantos estan, cuantos solo casan por la parte antes de la
@ (otro dominio) y cuantos no estan, por dominio.

Solo lectura. Por defecto mira solo los creadores de agentes
(`worker_manager.worker_manager_user`) del entity/environment que sincroniza
el servicio; con --all-users, toda la coleccion `user`:

    kubectl exec -n <ns> <pod> -- python scripts/check_maisa_users_in_workday.py

Con --emails imprime ademas los emails (missing = los que no estan en
Workday ni por la parte antes de la @; all = todos), uno por linea al final.
Son datos personales: redirigirlos a un fichero local y no commitearlo:

    kubectl exec -n <ns> <pod> -- python scripts/check_maisa_users_in_workday.py --emails missing > maisa_sin_workday.txt

Usa la misma BBDD que el servicio (SINC_AMN_INTERMEDIATE_DB_DSN) y la misma
conexion a Maisa.
"""

import argparse
import asyncio
import os
import sys
from collections import Counter
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grc"))

from sinc_amn.clients.maisa_client import MaisaClient  # noqa: E402
from sinc_amn.config import settings  # noqa: E402


async def _maisa_emails(all_users: bool) -> set[str]:
    db = MaisaClient()._db
    query = {}
    if not all_users:
        user_ids = await db.worker_manager.distinct(
            "worker_manager_user",
            {
                "entity": settings.maisa_workers_entity,
                "environment": settings.maisa_workers_environment,
                "is_deleted": False,
            },
        )
        query = {"user_id": {"$in": user_ids}}
    return {
        user["email"].strip().lower()
        async for user in db.user.find(query, {"email": 1})
        if user.get("email")
    }


def _domain(email: str) -> str:
    return email.split("@")[-1]


async def _check(all_users: bool, emails_mode: str | None) -> None:
    maisa = await _maisa_emails(all_users)
    conn = await asyncpg.connect(os.environ["SINC_AMN_INTERMEDIATE_DB_DSN"], timeout=10)
    try:
        rows = await conn.fetch("SELECT lower(email) AS email FROM workday_members")
    finally:
        await conn.close()
    workday = {r["email"] for r in rows if r["email"]}
    workday_locals = {e.split("@")[0] for e in workday}

    exact = {e for e in maisa if e in workday}
    by_local = {e for e in maisa - exact if e.split("@")[0] in workday_locals}
    missing = maisa - exact - by_local

    scope = (
        "toda la coleccion user"
        if all_users
        else "creadores de agentes de "
        f"{settings.maisa_workers_entity}/{settings.maisa_workers_environment}"
    )
    print(f"usuarios de Maisa ({scope}): {len(maisa)}")
    print(f"filas en workday_members:        {len(workday)}")
    print(f"  en Workday con el mismo email: {len(exact)}")
    print(f"  solo por la parte antes de @:  {len(by_local)}")
    print(f"  no estan:                      {len(missing)}")

    print("\npor dominio (mismo email / antes de @ / no estan):")
    domains = Counter(_domain(e) for e in maisa)
    for domain, total in domains.most_common():
        print(
            f"  {domain:<35} {total:>5}  "
            f"{sum(_domain(e) == domain for e in exact):>5} "
            f"{sum(_domain(e) == domain for e in by_local):>5} "
            f"{sum(_domain(e) == domain for e in missing):>5}"
        )

    if emails_mode:
        print(f"\nemails ({emails_mode}):")
        for email in sorted(missing if emails_mode == "missing" else maisa):
            print(email)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--all-users",
        action="store_true",
        help="toda la coleccion user, no solo los creadores de agentes",
    )
    parser.add_argument(
        "--emails",
        choices=["missing", "all"],
        help="imprime tambien los emails (datos personales)",
    )
    args = parser.parse_args()
    asyncio.run(_check(args.all_users, args.emails))


if __name__ == "__main__":
    main()
