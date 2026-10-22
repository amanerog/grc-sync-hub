import pytest

from sinc_amn.core.business_entity import business_entity_for
from sinc_amn.models.workday_member import WorkdayMember


def _member(business_unit, position_level_2, functional_group_1):
    return WorkdayMember(
        email="someone@example.com",
        business_unit=business_unit,
        position_level_2=position_level_2,
        functional_group_1=functional_group_1,
    )


@pytest.mark.parametrize(
    ("business_unit", "position_level_2", "functional_group_1", "expected"),
    [
        # A) Entidad legal: se ignoran business_unit y functional_group_1.
        ("CHQ", "SANES_8901 SANTANDER ESPAÑA", "IT", "Santander ES"),
        ("DCB", "SCONS_0000 Santander Consumer Group", "Finance", "Consumer"),
        ("CHQ", "Santander Mexico", "IT", "Santander MX"),
        ("CHQ", "Direccion General GFS", "IT", "Santander MX"),
        ("CHQ", "OPENB_0000 Openbank & Open Digital Services", "IT", "Openbank"),
        ("PGX", "SB001_00000 Brasil", "IT", "Santander BR"),
        ("CHQ", "Santander Perú", "Risk", "Santander PE"),
        ("CHQ", "Santander Portugal", "IT", "Santander PT"),
        ("CHQ", "Santander UK", "Finance", "Santander UK"),
        ("PGX", "SANCO_SDB0001 PagoNxt HoldCo", "PagoNxt Business",
         "Santander Payments Solutions"),
        # Entidad legal sin mapeo -> fallback.
        ("CHQ", "Santander Chile", "IT", "Other"),
        # B) HQ + CHQ/HQ: por functional_group_1.
        ("HQ", "Global & Corporate HQ", "Internal Audit", "HQ - Auditory"),
        ("CHQ", "Global & Corporate HQ", "Operational Processes", "HQ - T&O"),
        ("CHQ", "Global & Corporate HQ", "IT", "HQ - T&O"),
        ("HQ", "Global & Corporate HQ", "Financial Accounting and Mgmt Ctrl",
         "HQ - Finance Control de Gestion"),
        ("CHQ", "Global & Corporate HQ", "Other Support & Control", "HQ - Others"),
        # C) HQ + otra business_unit: por business_unit, sin sub-enrutar.
        ("CIB", "Global & Corporate HQ", "Data & AI", "CIB"),
        ("CRD", "Global & Corporate HQ", "Operational Processes", "Global Cards"),
        ("WM", "Global & Corporate HQ", "Data & AI", "WM&I"),
        ("RET", "Global & Corporate HQ", "Retail & Commercial", "R&C"),
        ("PGX", "Global & Corporate HQ", "IT", "Santander Payments Solutions"),
        ("OTH", "Global & Corporate HQ", "IT", "Other"),
    ],
)
def test_business_entity_for(business_unit, position_level_2, functional_group_1, expected):
    member = _member(business_unit, position_level_2, functional_group_1)
    assert business_entity_for(member) == expected


def test_business_entity_for_member_without_workday_data():
    assert business_entity_for(None) == "Other"


def test_business_entity_for_ignores_case_and_spacing():
    member = _member(" chq ", "global & corporate  hq", "data & ai")
    assert business_entity_for(member) == "HQ - Data & AI"
