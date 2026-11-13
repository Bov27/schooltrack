import uuid
from datetime import date, datetime
from typing import Annotated
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.modules.institutions.models import StaffType

_TIMEZONES = frozenset(available_timezones())


def _check_timezone(value: str) -> str:
    if value not in _TIMEZONES:
        raise ValueError(f"Unknown IANA timezone '{value}'")
    return value


Timezone = Annotated[str, AfterValidator(_check_timezone)]


class InstitutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    country: str
    timezone: str
    is_active: bool
    created_at: datetime


class InstitutionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=2, max_length=63, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    timezone: Timezone = "America/Bogota"
    admin_email: str | None = Field(
        default=None,
        max_length=320,
        description="Existing user to make the first School Admin of the institution.",
    )


class CampusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    institution_id: uuid.UUID
    name: str
    address: str | None
    timezone: str | None
    is_active: bool
    created_at: datetime


class CampusCreate(BaseModel):
    # extra="forbid": a client cannot even send institution_id; the tenant comes from
    # the authenticated membership (ADR-002).
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    timezone: Timezone | None = None


class StudentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_code: str = Field(min_length=1, max_length=50)
    full_name: str = Field(min_length=1, max_length=200)
    date_of_birth: date | None = None
    user_email: str | None = Field(
        default=None,
        max_length=320,
        description="Existing account that the student uses in the mobile app (optional).",
    )


class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_code: str
    full_name: str
    date_of_birth: date | None
    user_id: uuid.UUID | None
    is_active: bool


class StaffCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_code: str = Field(min_length=1, max_length=50)
    staff_type: StaffType
    user_email: str = Field(max_length=320)


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_code: str
    staff_type: StaffType
    user_id: uuid.UUID
    is_active: bool


class GuardianCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_email: str = Field(max_length=320)
    phone: str | None = Field(default=None, max_length=30)


class GuardianOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    phone: str | None
    student_ids: list[uuid.UUID]


class GuardianLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: uuid.UUID
    relationship: str = Field(min_length=2, max_length=50, examples=["MOTHER", "LEGAL_GUARDIAN"])
    receives_alerts: bool = True
