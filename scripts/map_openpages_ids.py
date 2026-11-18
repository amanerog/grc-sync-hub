"""Saca los ids de otra instancia de OpenPages (p.ej. PRO) para la tabla de
core/openpages_ids.py, buscando por nombre los fields y asociaciones de PRE.

Solo lectura (GET de las definiciones de tipo). La instancia de PRE es la
configurada en el pod; la otra se pasa por su ZEN instance id, y su API key
se pide por teclado (no va en los argumentos):

    kubectl exec -it -n <ns> <pod> -- python scripts/map_openpages_ids.py <zen_instance_id_pro>
"""

import argparse
import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grc"))

from sinc_amn.clients.auron_client import AuronClient  # noqa: E402
from sinc_amn.config import settings  # noqa: E402
from sinc_amn.core.openpages_ids import OPENPAGES_IDS  # noqa: E402

# typeDefinitionId en PRE de los tipos que llevan esos ids: Agent y AI Use Case.
_PRE_TYPE_IDS = (settings.auron_agent_type_definition_id, "94")


def _named_nodes(node):
    """Dicts con id y name en cualquier nivel (fields, asociaciones...),
    sin entrar en los valores de los enums: sus ids chocarian con los de los
    fields."""
    if isinstance(node, dict):
        if "id" in node and "name" in node:
            yield node
        for key, value in node.items():
            if key != "enumValues":
                yield from _named_nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from _named_nodes(item)


async def _type(auron: AuronClient, type_id: str) -> dict:
    response = await auron._request(
        "GET", f"/grc/api/types/{type_id}", headers=await auron._auth_headers()
    )
    response.raise_for_status()
    return response.json()


async def _main(zen_instance_id: str, api_key: str) -> None:
    pre_types = [await _type(AuronClient(), type_id) for type_id in _PRE_TYPE_IDS]
    pre_names = {
        str(node["id"]): node["name"] for t in pre_types for node in _named_nodes(t)
    }

    settings.auron_zen_instance_id = zen_instance_id
    settings.auron_api_key = api_key
    settings.auron_base_url = f"https://{zen_instance_id}.eu-de.openpages.cloud.ibm.com"
    other = AuronClient()
    # Los tipos se piden por nombre: su id tambien puede cambiar.
    other_types = [await _type(other, t["name"]) for t in pre_types]
    other_ids: dict[str, set[str]] = {}
    for t in other_types:
        for node in _named_nodes(t):
            other_ids.setdefault(node["name"], set()).add(str(node["id"]))

    for t, o in zip(pre_types, other_types, strict=True):
        print(f"tipo {t['name']}: PRE {t.get('id')} -> otra {o.get('id')}")
    print(f"\n{'clave':<28} {'PRE':>6} {'otra':>12} {'en tabla':>9}  nombre")
    for key, pre_id in OPENPAGES_IDS["PRE"].items():
        name = pre_names.get(pre_id)
        found = ",".join(sorted(other_ids.get(name, ()))) if name else ""
        current = OPENPAGES_IDS["PRO"][key] or "-"
        print(
            f"{key:<28} {pre_id:>6} {found or '?':>12} {current:>9}  {name or '(no encontrado en PRE)'}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("zen_instance_id", help="ZEN instance id de la otra instancia")
    args = parser.parse_args()
    api_key = getpass.getpass("API key de la otra instancia: ")
    asyncio.run(_main(args.zen_instance_id, api_key))


if __name__ == "__main__":
    main()
