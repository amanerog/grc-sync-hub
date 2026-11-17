import pytest

from sinc_amn.core.business_entity import business_entity_for


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
    ],
)
def test_business_entity_for_maps_maisa_entity(entity, expected):
    assert business_entity_for(entity) == expected


@pytest.mark.parametrize("entity", [None, "", "Narnia"])
def test_business_entity_for_returns_none_without_mapping(entity):
    assert business_entity_for(entity) is None
