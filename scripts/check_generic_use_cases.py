"""Comprueba que existen en Auron los casos de uso genericos de cada
Business Entity (Flujo 2, `settings.auron_maisa_generic_use_case_name`).

Solo lectura. Usa la misma busqueda que el servicio (nombre exacto dentro
del Engagement de Maisa) y la misma configuracion de Auron:

    kubectl exec -n <ns> <pod> -- python scripts/check_generic_use_cases.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "grc"))

from sinc_amn.clients.auron_client import AuronClient  # noqa: E402
from sinc_amn.config import settings  # noqa: E402
from sinc_amn.core.business_entity import (  # noqa: E402
    BUSINESS_UNIT_TO_BE,
    FG1_TO_BE,
    HQ_OTHERS,
    OTHER,
    POSITION_LEVEL2_TO_BE,
)


async def main() -> None:
    entities = (
        set(POSITION_LEVEL2_TO_BE.values())
        | set(FG1_TO_BE.values())
        | set(BUSINESS_UNIT_TO_BE.values())
        | {HQ_OTHERS, settings.auron_other_business_entity}
    ) - {OTHER}

    client = AuronClient()
    missing = []
    for be in sorted(entities):
        name = settings.auron_maisa_generic_use_case_name.format(business_entity=be)
        use_case_id = await client.get_use_case_id_by_name(name, "maisa")
        print(f"{'OK ' if use_case_id else 'NO '} {use_case_id or '-':>8}  {name}")
        if not use_case_id:
            missing.append(name)

    print(f"\n{len(entities) - len(missing)}/{len(entities)} encontrados")


if __name__ == "__main__":
    asyncio.run(main())
