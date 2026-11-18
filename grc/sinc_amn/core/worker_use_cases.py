"""Caso de uso de OpenPages de agentes de Maisa sin label, segun el Excel de
mapeos de Auron (id del agente en Maisa -> Resource ID del caso de uso).

Va despues de la label y antes de la entity (ver
`WorkerSyncService._resolve_use_case`). Los Resource ID son de una instancia
concreta de OpenPages, asi que hay un CSV por instancia
(`data/maisa_worker_use_cases_<pre|pro>.csv`, columnas `worker_id` y
`use_case_id`, generado con scripts/build_worker_use_cases_csv.py); sin
fichero para la instancia configurada, este paso no aplica.
"""

import csv
from functools import cache
from pathlib import Path

from sinc_amn.config import settings

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@cache
def _mapping(environment: str) -> dict[str, str]:
    path = DATA_DIR / f"maisa_worker_use_cases_{environment.lower()}.csv"
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {row["worker_id"]: row["use_case_id"] for row in csv.DictReader(f)}


def mapped_use_case_id(worker_id: str) -> str | None:
    """Resource ID del caso de uso del agente segun el Excel de Auron, o None."""
    return _mapping(settings.auron_openpages_environment).get(worker_id)
