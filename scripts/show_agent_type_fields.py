"""Muestra la definicion en OpenPages de fields del tipo Agent
(`settings.auron_agent_type_definition_id`): id, dataType, si es obligatorio
y, si es enum, sus valores. Sirve para saber que enviar en un field nuevo
(AuronClient.create_agent / update_agent).

Solo lectura. Filtra por nombre (contiene, sin distinguir mayusculas); sin
filtros, por defecto los campos que el workflow de Agents exige rellenos:

    kubectl exec -n <ns> <pod> -- python scripts/show_agent_type_fields.py
    kubectl exec -n <ns> <pod> -- python scripts/show_agent_type_fields.py "Agent Role"
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grc"))

from sinc_amn.clients.auron_client import AuronClient  # noqa: E402
from sinc_amn.config import settings  # noqa: E402

_WORKFLOW_FIELDS = ("Agent Role", "Agent Task", "Output type", "Interaction type", "Execution flow")


def _field_definitions(node):
    """Dicts con id, name y dataType en cualquier nivel de la respuesta."""
    if isinstance(node, dict):
        if {"id", "name", "dataType"} <= node.keys():
            yield node
        for value in node.values():
            yield from _field_definitions(value)
    elif isinstance(node, list):
        for item in node:
            yield from _field_definitions(item)


def _enum_names(field: dict) -> list[str]:
    values = field.get("enumValues") or []
    if isinstance(values, dict):
        values = values.get("enumValue") or []
    return [v.get("name") for v in values if isinstance(v, dict)]


async def _show(names: list[str]) -> None:
    auron = AuronClient()
    response = await auron._request(
        "GET",
        f"/grc/api/types/{settings.auron_agent_type_definition_id}",
        headers=await auron._auth_headers(),
    )
    response.raise_for_status()
    wanted = [n.lower() for n in names]
    seen = set()
    for field in _field_definitions(response.json()):
        name = str(field.get("name"))
        if field["id"] in seen or not any(w in name.lower() for w in wanted):
            continue
        seen.add(field["id"])
        print(
            f"\n{field['id']:<6} {name}  dataType={field.get('dataType')} "
            f"required={field.get('required', field.get('isRequired'))}"
        )
        for value in _enum_names(field):
            print(f"    - {value}")
    if not seen:
        print("Ningun field coincide.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help="Texto que contiene el nombre del field")
    args = parser.parse_args()
    asyncio.run(_show(args.names or list(_WORKFLOW_FIELDS)))


if __name__ == "__main__":
    main()
