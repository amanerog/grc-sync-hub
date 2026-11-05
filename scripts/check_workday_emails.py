"""Revisa por que un email no casa con workday_members: muestra el reparto
de dominios de la tabla y, para cada email dado, si su usuario (la parte
antes de la @) aparece con otro dominio.

Solo lectura:

    kubectl exec -n <ns> <pod> -- python scripts/check_workday_emails.py nombre.apellido@gruposantander.es otro@gruposantander.com

Usa la misma BBDD que el servicio (SINC_AMN_INTERMEDIATE_DB_DSN).
"""

import argparse
import asyncio
import os

import asyncpg


async def _check(emails: list[str]) -> None:
    conn = await asyncpg.connect(os.environ["SINC_AMN_INTERMEDIATE_DB_DSN"], timeout=10)
    try:
        rows = await conn.fetch(
            "SELECT lower(split_part(email, '@', 2)) AS domain, count(*) "
            "FROM workday_members GROUP BY 1 ORDER BY 2 DESC"
        )
        print("dominios en workday_members:")
        for row in rows:
            print(f"  {row['domain']:<40} {row['count']}")

        if emails:
            print("\nemails, buscando por la parte antes de la @:")
        for email in emails:
            matches = await conn.fetch(
                "SELECT email FROM workday_members "
                "WHERE lower(split_part(email, '@', 1)) = $1",
                email.split("@")[0].lower(),
            )
            found = ", ".join(r["email"] for r in matches) or "nada"
            print(f"  {email:<45} -> {found}")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("emails", nargs="*", help="emails a buscar")
    asyncio.run(_check(parser.parse_args().emails))


if __name__ == "__main__":
    main()
