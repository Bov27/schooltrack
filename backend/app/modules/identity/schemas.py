import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.modules.institutions.models import InstitutionRole


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Only the email is trimmed: whitespace in a password is significant.
    email: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+$"
        ),
    ]
    password: str = Field(min_length=1, max_length=1024)


class RefreshRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1, max_length=4096)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - OAuth2 token kind
    expires_in: int = Field(description="Access token lifetime in seconds")


class MembershipOut(BaseModel):
    institution_id: uuid.UUID
    institution_name: str
    roles: list[InstitutionRole]


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_platform_admin: bool
    memberships: list[MembershipOut]
