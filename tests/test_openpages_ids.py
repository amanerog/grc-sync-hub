import pytest

from sinc_amn.config import settings
from sinc_amn.core.openpages_ids import OPENPAGES_IDS, openpages_id


def test_every_instance_lists_the_same_keys():
    assert OPENPAGES_IDS["PRO"].keys() == OPENPAGES_IDS["PRE"].keys()


def test_openpages_id_uses_the_configured_instance(monkeypatch):
    assert openpages_id("platform_agent_id") == "3658"

    monkeypatch.setattr(settings, "auron_openpages_environment", "PRO")

    assert openpages_id("platform_agent_id") == "3524"


def test_openpages_id_fails_when_the_id_is_unknown(monkeypatch):
    monkeypatch.setattr(settings, "auron_openpages_environment", "PRO")
    monkeypatch.setitem(OPENPAGES_IDS["PRO"], "platform_agent_id", None)

    with pytest.raises(LookupError, match="platform_agent_id"):
        openpages_id("platform_agent_id")
