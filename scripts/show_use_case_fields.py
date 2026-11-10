"""Muestra como vienen en OpenPages los fields que Flujo 2 escribe en el
caso de uso ("3601" Initiative, "3408" API ID, "3405" cuenta cloud): su
dataType y su valor actual. Sirve para comprobar el formato antes de
escribirlos (WorkerSyncService._update_use_case).

Solo lectura. Con ids, esos casos de uso; sin ids, los primeros casos de uso
reales (no genericos) de Maisa de la tabla intermedia:

    kubectl exec -n <ns> <pod> -- python scripts/show_use_case_fields.py
    kubectl exec -n <ns> <pod> -- python scripts/show_use_case_fields.py 51571 --all
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grc"))

from sinc_amn.clients.auron_client import AuronClient  # noqa: E402
from sinc_amn.config import settings  # noqa: E402

_FIELD_IDS = ("3601", "3408", "3405")


async def _real_use_case_ids(limit: int) -> list[str]:
    prefix = settings.auron_maisa_generic_use_case_name.split("{business_entity}")[0]
    conn = await asyncpg.connect(os.environ["SINC_AMN_INTERMEDIATE_DB_DSN"], timeout=10)
    try:
        rows = await conn.fetch(
            "SELECT source_resource_id FROM maisa_use_case_labels "
            "WHERE organization_id = $1 AND NOT is_deleted AND name NOT LIKE $2 "
            "ORDER BY updated_at DESC LIMIT $3",
            settings.maisa_organization_id,
            prefix + "%",
            limit,
        )
    finally:
        await conn.close()
    return [r["source_resource_id"] for r in rows]


async def _show(ids: list[str], show_all: bool, limit: int) -> None:
    ids = ids or await _real_use_case_ids(limit)
    auron = AuronClient()
    for resource_id in ids:
        content = await auron.get_use_case_content(resource_id)
        fields = (content.get("fields") or {}).get("field") or []
        print(f"\n{resource_id}  {content.get('name')}")
        by_id = {f.get("id"): f for f in fields}
        for field_id in _FIELD_IDS:
            field = by_id.get(field_id)
            if field is None:
                print(f"  {field_id}: no viene (vacio)")
            else:
                print(
                    f"  {field_id}: {field.get('name')!r} "
                    f"dataType={field.get('dataType')} value={field.get('value')!r}"
                )
        if show_all:
            print("  todos los fields:")
            for field in fields:
                print(
                    f"    {field.get('id'):<6} {field.get('dataType'):<14} "
                    f"{field.get('name')}"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ids", nargs="*", help="Resource IDs de casos de uso")
    parser.add_argument(
        "--all", action="store_true", help="lista tambien id/dataType/nombre de todos los fields"
    )
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(_show(args.ids, args.all, args.limit))


if __name__ == "__main__":
    main()
