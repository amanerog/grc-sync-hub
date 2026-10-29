"""Muestra el esquema de una coleccion de la DocumentDB de Maisa: que
campos tiene, en cuantos documentos aparece cada uno y de que tipo es.

Solo lectura y sin valores (la coleccion `user` tiene datos personales):

    kubectl exec -n <ns> <pod> -- python scripts/inspect_maisa_collection.py user

Los subdocumentos se recorren con notacion `a.b`; en las listas se mira
dentro de sus elementos (`a[].b`). Usa la misma conexion que el servicio.
"""

import argparse
import asyncio
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grc"))

from sinc_amn.clients.maisa_client import MaisaClient  # noqa: E402


def _walk(value, path: str, fields: dict[str, Counter], seen: set[str]) -> None:
    if path:
        fields[path][type(value).__name__] += 1
        seen.add(path)
    if isinstance(value, dict):
        for key, child in value.items():
            _walk(child, f"{path}.{key}" if path else key, fields, seen)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, (dict, list)):
                _walk(item, f"{path}[]", fields, seen)


async def _inspect(collection: str, limit: int) -> None:
    db = MaisaClient()._db
    fields: dict[str, Counter] = defaultdict(Counter)
    presence: Counter = Counter()
    total = 0
    async for document in db[collection].find({}, limit=limit):
        total += 1
        seen: set[str] = set()
        _walk(document, "", fields, seen)
        presence.update(seen)

    print(f"coleccion {collection!r}: {total} documentos revisados\n")
    width = max((len(path) for path in fields), default=0)
    for path in sorted(fields):
        types = ", ".join(name for name, _ in fields[path].most_common())
        print(f"{path:<{width}}  {presence[path]:>7}  {types}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("collection", nargs="?", default="user")
    parser.add_argument(
        "--limit", type=int, default=0, help="maximo de documentos (0 = todos)"
    )
    args = parser.parse_args()
    asyncio.run(_inspect(args.collection, args.limit))


if __name__ == "__main__":
    main()
