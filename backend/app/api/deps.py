"""Request-scoped dependencies: database sessions, authentication, tenant context, roles.

Order for a tenant-scoped endpoint:
    bearer token -> CurrentUser (app.current_user_id set)
                 -> TenantContext (membership checked, app.current_institution_id set)
                 -> require_roles(...)
All of it runs inside the same database transaction as the endpoint's queries.
"""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import (
    AuthenticationError,
    DomainError,
    PermissionDeniedError,
    ServiceUnavailableError,
)
from app.core.security import InvalidTokenError, decode_token
from app.infrastructure.database import Database
from app.infrastructure.orm import set_current_institution, set_current_user
from app.modules.identity.models import User
from app.modules.identity.service import IdentityService
from app.modules.institutions.models import InstitutionRole
from app.modules.institutions.service import InstitutionService

_bearer = HTTPBearer(auto_error=False, description="Access token from POST /auth/login")


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_database(request: Request) -> Database:
    database: Database = request.app.state.database
    return database


async def get_session(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    """Runtime-role session. Services commit explicitly; anything uncommitted is rolled
    back when the session closes, together with the transaction-local tenant settings."""
    async for session in database.session():
        yield session


async def get_platform_session(
    database: Annotated[Database, Depends(get_database)],
) -> AsyncIterator[AsyncSession]:
    if database.platform_session_factory is None:
        raise ServiceUnavailableError("Platform operations are not configured")
    async with database.platform_session_factory() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise AuthenticationError("Not authenticated")
    try:
        claims = decode_token(settings, credentials.credentials, "access")
    except InvalidTokenError as exc:
        raise AuthenticationError("Invalid or expired access token") from exc

    user = await IdentityService(session, settings).get_active_user(claims.subject)
    if user is None:
        raise AuthenticationError("Invalid or expired access token")
    await set_current_user(session, user.id)
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


@dataclass(frozen=True, slots=True)
class TenantContext:
    user_id: uuid.UUID
    institution_id: uuid.UUID
    roles: frozenset[InstitutionRole]

    def has_any(self, *roles: InstitutionRole) -> bool:
        return bool(self.roles.intersection(roles))


async def get_tenant(
    user: CurrentUserDep,
    session: SessionDep,
    x_institution_id: Annotated[
        uuid.UUID | None,
        Header(
            description=(
                "Institution to act in. Optional when the user belongs to exactly one "
                "institution. Only honoured if the user is an active member."
            )
        ),
    ] = None,
) -> TenantContext:
    membership = await InstitutionService(session).active_membership(user.id, x_institution_id)
    if membership is None:
        if x_institution_id is None:
            raise DomainError(
                "X-Institution-Id header is required for users in several institutions"
            )
        # Same answer whether the institution exists or not: no enumeration.
        raise PermissionDeniedError("You are not an active member of this institution")
    await set_current_institution(session, membership.institution_id)
    return TenantContext(user.id, membership.institution_id, membership.roles)


TenantDep = Annotated[TenantContext, Depends(get_tenant)]


def require_roles(*roles: InstitutionRole) -> Callable[[TenantContext], Awaitable[TenantContext]]:
    allowed = frozenset(roles)

    async def checker(tenant: TenantDep) -> TenantContext:
        if not tenant.roles & allowed:
            raise PermissionDeniedError("Your role does not allow this action")
        return tenant

    return checker


async def require_platform_admin(
    user: CurrentUserDep, session: SessionDep, settings: SettingsDep
) -> User:
    if not await IdentityService(session, settings).is_platform_admin(user.id):
        raise PermissionDeniedError("Platform administrator role required")
    return user


PlatformAdminDep = Annotated[User, Depends(require_platform_admin)]
SchoolAdminDep = Annotated[TenantContext, Depends(require_roles(InstitutionRole.SCHOOL_ADMIN))]
PlatformSessionDep = Annotated[AsyncSession, Depends(get_platform_session)]
