import uuid
from datetime import datetime
from typing import Annotated
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

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
