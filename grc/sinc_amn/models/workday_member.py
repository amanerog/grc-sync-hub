from pydantic import BaseModel


class WorkdayMember(BaseModel):
    """Datos de Workday de un empleado (tabla `workday_members`)."""

    email: str
    business_unit: str | None = None
    position_level_2: str | None = None
    functional_group_1: str | None = None
    country: str | None = None
