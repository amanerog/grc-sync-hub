"""Genera grc/sinc_amn/data/maisa_worker_use_cases_<instancia>.csv a partir del
Excel de mapeos de Auron (agente de Maisa -> caso de uso de OpenPages).

Del Excel solo se guardan dos columnas: el id del agente en Maisa
(`Column1.wmid`, el `worker_manager`) y el Resource ID del caso de uso
(`AuronID`), de las filas con Result "Auron Case exists". Hay una fila por
version del agente: si dos versiones apuntan a casos de uso distintos, gana la
de version mas alta y se avisa.

Se ejecuta en local (necesita openpyxl, no va en la imagen):

    python scripts/build_worker_use_cases_csv.py mapeos.xlsx --instance pro
"""

import argparse
import csv
import sys
from pathlib import Path

from openpyxl import load_workbook

_DATA_DIR = Path(__file__).resolve().parent.parent / "grc" / "sinc_amn" / "data"
_WORKER = "Column1.wmid"
_USE_CASE = "AuronID"
_RESULT = "Result"
_VERSION = "Column1.version"
_EXISTS = "Auron Case exists"


def _rows(path: Path, sheet: str | None):
    workbook = load_workbook(path, read_only=True, data_only=True)
    ws = workbook[sheet] if sheet else workbook.active
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(rows)]
    missing = {_WORKER, _USE_CASE, _RESULT, _VERSION} - set(header)
    if missing:
        sys.exit(f"Faltan columnas en el Excel: {sorted(missing)} (hay: {header})")
    for row in rows:
        yield dict(zip(header, row, strict=False))


def _as_id(value) -> str:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip() if value is not None else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("excel", type=Path)
    parser.add_argument("--instance", required=True, choices=["pre", "pro"])
    parser.add_argument("--sheet", help="hoja (por defecto, la activa)")
    args = parser.parse_args()

    best: dict[str, tuple[int, str]] = {}
    conflicts: set[str] = set()
    read = kept = 0
    for row in _rows(args.excel, args.sheet):
        read += 1
        worker_id, use_case_id = _as_id(row[_WORKER]), _as_id(row[_USE_CASE])
        if row[_RESULT] != _EXISTS or not worker_id or not use_case_id:
            continue
        kept += 1
        version = int(row[_VERSION] or 0)
        current = best.get(worker_id)
        if current is not None and current[1] != use_case_id:
            conflicts.add(worker_id)
        if current is None or version > current[0]:
            best[worker_id] = (version, use_case_id)

    out = _DATA_DIR / f"maisa_worker_use_cases_{args.instance}.csv"
    out.parent.mkdir(exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["worker_id", "use_case_id"])
        for worker_id in sorted(best):
            writer.writerow([worker_id, best[worker_id][1]])

    print(f"{read} filas leidas, {kept} con caso de uso, {len(best)} agentes -> {out}")
    for worker_id in sorted(conflicts):
        print(f"  aviso: {worker_id} tiene versiones en casos de uso distintos, "
              f"se usa {best[worker_id][1]}")


if __name__ == "__main__":
    main()
