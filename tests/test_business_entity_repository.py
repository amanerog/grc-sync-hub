from sinc_amn.models.workday_member import WorkdayMember
from sinc_amn.repositories.business_entity_repository import (
    BusinessEntityRepository,
)

from ._asyncpg_fakes import FakeConnection, FakePool


async def test_get_member_matches_email_lowercased():
    conn = FakeConnection(
        fetchrow_results=[
            {
                "email": "ana@example.com",
                "business_unit": "HQ",
                "position_level_2": "Global & Corporate HQ",
                "functional_group_1": "Legal",
                "country": "Spain",
            }
        ]
    )
    repo = BusinessEntityRepository(FakePool(conn))

    member = await repo.get_member(" Ana@Example.com ")

    assert member == WorkdayMember(
        email="ana@example.com",
        business_unit="HQ",
        position_level_2="Global & Corporate HQ",
        functional_group_1="Legal",
        country="Spain",
    )
    query, args = conn.fetchrow_calls[0]
    assert "lower($1)" in query
    assert args == ("Ana@Example.com",)


async def test_get_member_returns_none_when_missing():
    repo = BusinessEntityRepository(FakePool(FakeConnection()))

    assert await repo.get_member("nobody@example.com") is None
