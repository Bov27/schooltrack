from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    CurrentUserDep,
    PlatformAdminDep,
    PlatformSessionDep,
    SessionDep,
    SettingsDep,
    TenantContext,
    TenantDep,
    require_roles,
)
from app.api.errors import error_responses
from app.core.errors import NotFoundError
from app.modules.identity.service import IdentityService
from app.modules.institutions.models import InstitutionRole
from app.modules.institutions.schemas import (
    CampusCreate,
    CampusOut,
    InstitutionCreate,
    InstitutionOut,
)
from app.modules.institutions.service import InstitutionService

router = APIRouter()

SchoolAdminDep = Annotated[
    TenantContext, Depends(require_roles(InstitutionRole.SCHOOL_ADMIN))
]

_errors = error_responses(401, 403, 409)


@router.get("/institutions", response_model=list[InstitutionOut], tags=["institutions"])
async def list_institutions(user: CurrentUserDep, session: SessionDep) -> list[InstitutionOut]:
    """Institutions where the caller is an active member."""
    institutions = await InstitutionService(session).list_my_institutions(user.id)
    return [InstitutionOut.model_validate(i) for i in institutions]


@router.post(
    "/institutions",
    response_model=InstitutionOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409),
    tags=["institutions"],
)
async def create_institution(
    body: InstitutionCreate,
    admin: PlatformAdminDep,
    platform_session: PlatformSessionDep,
    settings: SettingsDep,
) -> InstitutionOut:
    """Super Admin only. Optionally makes an existing user the first School Admin."""
    admin_user_id = None
    if body.admin_email is not None:
        admin_user_id = await IdentityService(platform_session, settings).find_user_id_by_email(
            body.admin_email
        )
        if admin_user_id is None:
            raise NotFoundError("No active user with that admin_email")
    institution = await InstitutionService(platform_session).create_institution(
        name=body.name,
        slug=body.slug,
        timezone=body.timezone,
        admin_user_id=admin_user_id,
        granted_by=admin.id,
    )
    return InstitutionOut.model_validate(institution)


@router.get("/campuses", response_model=list[CampusOut], responses=_errors, tags=["campuses"])
async def list_campuses(tenant: TenantDep, session: SessionDep) -> list[CampusOut]:
    campuses = await InstitutionService(session).list_campuses(tenant.institution_id)
    return [CampusOut.model_validate(c) for c in campuses]


@router.post(
    "/campuses",
    response_model=CampusOut,
    status_code=status.HTTP_201_CREATED,
    responses=_errors,
    tags=["campuses"],
)
async def create_campus(
    body: CampusCreate,
    session: SessionDep,
    tenant: SchoolAdminDep,
) -> CampusOut:
    campus = await InstitutionService(session).create_campus(
        tenant.institution_id, name=body.name, address=body.address, timezone=body.timezone
    )
    return CampusOut.model_validate(campus)
