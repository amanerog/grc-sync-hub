"""Muestra la estructura de una BBDD Postgres: bases de datos, y en la
indicada sus tablas por esquema con el numero de filas (y con --columns,
las columnas y su tipo). Nunca imprime valores.

Solo lectura (sesion en modo read-only). La password se lee por stdin para
que no quede en el historial ni en los argumentos del proceso:

    kubectl exec -i -n <ns> <pod> -- python scripts/inspect_postgres.py --host <host> --user <usuario> --database <bd>

y se escribe la password + Enter. Sin --host usa la BBDD del servicio
(SINC_AMN_INTERMEDIATE_DB_DSN) y no pide password.
"""

import argparse
import asyncio
import os
import sys

import asyncpg

_TABLES = """
SELECT n.nspname AS schema, c.relname AS name, c.reltuples::bigint AS estimate
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p')
  AND n.nspname NOT IN ('pg_catalog', 'information_schema')
  AND n.nspname NOT LIKE 'pg_toast%'
ORDER BY 1, 2
"""

_COLUMNS = """
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = $1 AND table_name = $2
ORDER BY ordinal_position
"""


async def _connect(args) -> asyncpg.Connection:
    if not args.host:
        return await asyncpg.connect(
            os.environ["SINC_AMN_INTERMEDIATE_DB_DSN"], timeout=10
        )
    password = sys.stdin.readline().rstrip("\r\n")
    return await asyncpg.connect(
        host=args.host,
        port=args.port,
        user=args.user,
        password=password,
        database=args.database,
        ssl="require",
        timeout=10,
    )


async def _inspect(args) -> None:
    conn = await _connect(args)
    try:
        await conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        print(await conn.fetchval("SELECT version()"))
        print(f"conectado a: {await conn.fetchval('SELECT current_database()')}")

        databases = await conn.fetch(
            "SELECT datname FROM pg_database WHERE NOT datistemplate ORDER BY 1"
        )
        print("\nbases de datos: " + ", ".join(r["datname"] for r in databases))

        tables = await conn.fetch(_TABLES)
        print(f"\n{len(tables)} tablas:")
        for table in tables:
            name = f"{table['schema']}.{table['name']}"
            if args.exact:
                ident = f'"{table["schema"]}"."{table["name"]}"'
                count = await conn.fetchval(f"SELECT count(*) FROM {ident}")
            else:
                # reltuples: estimacion de Postgres, -1 si nunca se ha analizado.
                count = table["estimate"] if table["estimate"] >= 0 else "?"
            print(f"  {name:<60} {count}")
            if args.columns:
                for col in await conn.fetch(_COLUMNS, table["schema"], table["name"]):
                    nullable = "" if col["is_nullable"] == "YES" else " not null"
                    print(f"      {col['column_name']:<40} {col['data_type']}{nullable}")
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--host", help="sin --host, la BBDD del servicio")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user")
    parser.add_argument("--database", default="postgres")
    parser.add_argument("--columns", action="store_true", help="lista las columnas")
    parser.add_argument(
        "--exact", action="store_true", help="count(*) exacto en vez de estimacion"
    )
    args = parser.parse_args()
    if args.host and not args.user:
        parser.error("--user es obligatorio con --host")
    asyncio.run(_inspect(args))


if __name__ == "__main__":
    main()
