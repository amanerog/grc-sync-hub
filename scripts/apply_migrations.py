"""Aplica migraciones SQL de db/migrations/ contra la tabla intermedia.

Las migraciones ya van en la imagen, asi que se lanza desde fuera del pod
pasando las rutas en el orden en que hay que aplicarlas:

    kubectl exec -n <ns> <pod> -- python scripts/apply_migrations.py db/migrations/0009_create_workday_members.sql

Cada fichero se ejecuta tal cual y en una transaccion propia: si uno falla
se para ahi, sin aplicar los siguientes. Usa la misma BBDD que el servicio
(SINC_AMN_INTERMEDIATE_DB_DSN).
"""

import argparse
import asyncio
import os
from pathlib import Path

import asyncpg


async def _apply(paths: list[Path]) -> None:
    conn = await asyncpg.connect(os.environ["SINC_AMN_INTERMEDIATE_DB_DSN"], timeout=10)
    try:
        for path in paths:
            async with conn.transaction():
                await conn.execute(path.read_text(encoding="utf-8"))
            print("aplicada", path)
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="ficheros .sql")
    asyncio.run(_apply(parser.parse_args().paths))


if __name__ == "__main__":
    main()
