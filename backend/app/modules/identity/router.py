from fastapi import APIRouter, status

from app.api.deps import CurrentUserDep, SessionDep, SettingsDep
from app.api.errors import ErrorResponse
from app.modules.identity.schemas import (
    LoginRequest,
    MeResponse,
    MembershipOut,
    RefreshRequest,
    TokenResponse,
)
from app.modules.identity.service import IdentityService, TokenPair
from app.modules.institutions.service import InstitutionService

router = APIRouter(tags=["auth"])

_401 = {401: {"model": ErrorResponse}}


def _token_response(pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token, refresh_token=pair.refresh_token, expires_in=pair.expires_in
    )


@router.post("/auth/login", response_model=TokenResponse, responses=_401)
async def login(body: LoginRequest, session: SessionDep, settings: SettingsDep) -> TokenResponse:
    pair = await IdentityService(session, settings).login(body.email, body.password)
    return _token_response(pair)


@router.post("/auth/refresh", response_model=TokenResponse, responses=_401)
async def refresh(
    body: RefreshRequest, session: SessionDep, settings: SettingsDep
) -> TokenResponse:
    """Rotates the refresh token: the one sent is revoked and a new pair is returned.
    Presenting an already-rotated token revokes the whole login."""
    pair = await IdentityService(session, settings).refresh(body.refresh_token)
    return _token_response(pair)


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, session: SessionDep, settings: SettingsDep) -> None:
    await IdentityService(session, settings).logout(body.refresh_token)


@router.get("/users/me", response_model=MeResponse, responses=_401, tags=["users"])
async def me(user: CurrentUserDep, session: SessionDep, settings: SettingsDep) -> MeResponse:
    identity = IdentityService(session, settings)
    memberships = await InstitutionService(session).memberships_for(user.id)
    return MeResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_platform_admin=await identity.is_platform_admin(user.id),
        memberships=[
            MembershipOut(
                institution_id=m.institution_id,
                institution_name=m.institution_name,
                roles=m.roles,
            )
            for m in memberships
        ],
    )
