"""Carga el CSV de Workday en la tabla workday_members (Flujo 2, caso de
uso generico de cada Business Entity).

El CSV ("Miembros,Business Unit,Position Level 2,Functional Group 1,
Country") llega por stdin, asi que se lanza desde fuera del pod sin copiar
nada al contenedor:

    kubectl exec -i -n <ns> <pod> -- python scripts/load_reference_data.py workday < miembros.csv

Sustituye entera la tabla y muestra cuantos empleados caen en cada Business
Entity. Usa la misma BBDD que el servicio (SINC_AMN_INTERMEDIATE_DB_DSN).
"""

import argparse
import asyncio
import csv
import io
import os
import sys
from collections import Counter
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grc"))

from sinc_amn.core.business_entity import business_entity_for  # noqa: E402
from sinc_amn.models.workday_member import WorkdayMember  # noqa: E402

_WORKDAY_COLUMNS = {
    "Miembros": "email",
    "Business Unit": "business_unit",
    "Position Level 2": "position_level_2",
    "Functional Group 1": "functional_group_1",
    "Country": "country",
}
_NOT_FOUND = "** No encontrado"


def _read_csv() -> list[dict]:
    raw = sys.stdin.buffer.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        # CSV guardado desde Excel en Windows.
        text = raw.decode("cp1252")
    return list(csv.DictReader(io.StringIO(text)))


def _workday_members(rows: list[dict]) -> tuple[dict[str, WorkdayMember], Counter]:
    missing = set(_WORKDAY_COLUMNS) - set(rows[0] if rows else {})
    if missing:
        sys.exit(f"Faltan columnas en el CSV: {sorted(missing)}")

    stats = Counter()
    members: dict[str, WorkdayMember] = {}
    for row in rows:
        values = {field: (row[column] or "").strip() for column, field in _WORKDAY_COLUMNS.items()}
        email = values.pop("email").lower()
        if not email:
            continue
        stats["leidas"] += 1
        if values["business_unit"] == _NOT_FOUND:
            stats["no encontrado (se omiten)"] += 1
            continue
        if email in members:
            stats["duplicadas"] += 1
        members[email] = WorkdayMember(email=email, **{k: v or None for k, v in values.items()})
    stats["cargadas"] = len(members)
    return members, stats


async def _load_workday(conn: asyncpg.Connection, rows: list[dict]) -> None:
    members, stats = _workday_members(rows)
    async with conn.transaction():
        await conn.execute("DELETE FROM workday_members")
        await conn.executemany(
            """
            INSERT INTO workday_members
                (email, business_unit, position_level_2, functional_group_1, country)
            VALUES ($1, $2, $3, $4, $5)
            """,
            [
                (m.email, m.business_unit, m.position_level_2, m.functional_group_1, m.country)
                for m in members.values()
            ],
        )
    for key, value in stats.items():
        print(f"{key:28} {value}")

    print("\nBusiness Entity resultante:")
    by_entity = Counter(business_entity_for(m) for m in members.values())
    for entity, count in by_entity.most_common():
        print(f"  {entity:40} {count}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("kind", choices=["workday"])
    parser.parse_args()

    rows = _read_csv()
    conn = await asyncpg.connect(os.environ["SINC_AMN_INTERMEDIATE_DB_DSN"], timeout=10)
    try:
        await _load_workday(conn, rows)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
