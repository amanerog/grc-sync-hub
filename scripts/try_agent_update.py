"""Prueba por partes el PUT de update_agent contra un Agent de OpenPages
para ver que parte rechaza: solo `name`, y cada field ("3261", "3293",
"3290") por separado, sin y con su `name`.

Cada PUT reescribe el valor que el Agent YA tiene (leido con un GET justo
antes), asi que no cambia nada. Imprime el status y el cuerpo de cada
respuesta (no los valores de los fields, que llevan emails):

    kubectl exec -n <ns> <pod> -- python scripts/try_agent_update.py 54161

Con --dry solo hace el GET y lista los fields del Agent.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grc"))

from sinc_amn.clients.auron_client import AuronClient  # noqa: E402

_FIELD_IDS = ("3261", "3293", "3290")


async def _put(auron: AuronClient, agent_id: str, label: str, payload: dict) -> None:
    headers = await auron._auth_headers()
    response = await auron._request(
        "PUT", f"/grc/api/contents/{agent_id}", headers=headers, json=payload
    )
    body = "" if response.is_success else " " + response.text[:500]
    print(f"  {label:<45} -> {response.status_code}{body}")


async def _try(agent_id: str, dry: bool) -> None:
    auron = AuronClient()
    content = await auron.get_use_case_content(agent_id)
    fields = {f.get("id"): f for f in (content.get("fields") or {}).get("field") or []}
    print(
        f"{agent_id}  typeDefinitionId={content.get('typeDefinitionId')} "
        f"primaryParentId={content.get('primaryParentId')} "
        f"description={'si' if content.get('description') else 'no'}"
    )
    for field in fields.values():
        has_value = "con valor" if field.get("value") not in (None, "") else "vacio"
        print(f"  {field.get('id'):<6} {field.get('dataType'):<14} {field.get('name')} ({has_value})")
    for field_id in _FIELD_IDS:
        if field_id not in fields:
            print(f"  {field_id}: no viene en el GET")
    if dry:
        return

    print("\nPUTs (reescriben el valor actual):")
    name = content["name"]
    await _put(auron, agent_id, "solo name", {"name": name})
    for field_id in _FIELD_IDS:
        current = fields.get(field_id, {})
        field = {
            "id": field_id,
            "dataType": current.get("dataType", "STRING_TYPE"),
            "hasChanged": True,
            "value": current.get("value"),
        }
        await _put(
            auron, agent_id, f"{field_id} sin name",
            {"name": name, "fields": {"field": [field]}},
        )
        if current.get("name"):
            await _put(
                auron, agent_id, f"{field_id} con name",
                {"name": name, "fields": {"field": [{**field, "name": current["name"]}]}},
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("agent_id")
    parser.add_argument("--dry", action="store_true", help="solo el GET")
    args = parser.parse_args()
    asyncio.run(_try(args.agent_id, args.dry))


if __name__ == "__main__":
    main()
