from sinc_amn.config import settings
from sinc_amn.core import worker_use_cases


def test_mapped_use_case_id_reads_the_csv_of_the_configured_instance(
    monkeypatch, tmp_path
):
    (tmp_path / "maisa_worker_use_cases_pro.csv").write_text(
        "worker_id,use_case_id\nWM-1,71245\n", encoding="utf-8"
    )
    monkeypatch.setattr(worker_use_cases, "DATA_DIR", tmp_path)
    worker_use_cases._mapping.cache_clear()
    monkeypatch.setattr(settings, "auron_openpages_environment", "PRO")

    assert worker_use_cases.mapped_use_case_id("WM-1") == "71245"
    assert worker_use_cases.mapped_use_case_id("WM-2") is None

    # Sin fichero para la instancia (PRE): el paso no aplica.
    monkeypatch.setattr(settings, "auron_openpages_environment", "PRE")
    assert worker_use_cases.mapped_use_case_id("WM-1") is None
    worker_use_cases._mapping.cache_clear()
