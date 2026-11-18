import pytest

from sinc_amn.core.business_entity import business_entity_for, is_skipped_entity


@pytest.mark.parametrize(
    ("entity", "expected"),
    [
        ("Spain", "Santander ES"),
        ("SPAIN", "Santander ES"),
        (" Spain ", "Santander ES"),
        ("Consumer", "Consumer"),
        ("Germany", "Consumer"),
        ("Global_Cards", "Global Cards"),
        ("HQ", "HQ - Others"),
        ("HQNEW", "HQ - Others"),
        ("Perú", "Santander PE"),
        ("Santander Payments Solutions", "Santander Payments Solutions"),
        ("WM&I", "WM&I"),
        ("SDS", "Other"),
        ("SCF_Global", "Consumer"),
        ("GETNET", "Santander Payments Solutions"),
    ],
)
def test_business_entity_for_maps_maisa_entity(entity, expected):
    assert business_entity_for(entity) == expected


@pytest.mark.parametrize("entity", [None, "", "Narnia"])
def test_business_entity_for_returns_none_without_mapping(entity):
    assert business_entity_for(entity) is None


def test_is_skipped_entity_only_for_platform():
    assert is_skipped_entity("Platform")
    assert is_skipped_entity(" PLATFORM ")
    assert not is_skipped_entity("Spain")
    assert not is_skipped_entity(None)
