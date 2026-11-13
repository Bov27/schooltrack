import uuid

from fastapi import APIRouter, Request, status

from app.api.deps import (
    CurrentUserDep,
    PlatformAdminDep,
    PlatformSessionDep,
    SchoolAdminDep,
    SessionDep,
    SettingsDep,
    TenantDep,
)
from app.api.errors import error_responses
from app.core.errors import NotFoundError, PermissionDeniedError
from app.modules.audit.service import AuditService
from app.modules.identity.service import IdentityService
from app.modules.institutions.models import InstitutionRole
from app.modules.institutions.schemas import (
    AdminAssign,
    CampusCreate,
    CampusOut,
    GuardianCreate,
    GuardianLink,
    GuardianOut,
    InstitutionCreate,
    InstitutionOut,
    PlatformInstitutionOut,
    StaffCreate,
    StaffOut,
    StudentCreate,
    StudentOut,
)
from app.modules.institutions.service import InstitutionService

router = APIRouter()

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


@router.get(
    "/platform/institutions",
    response_model=list[PlatformInstitutionOut],
    responses=error_responses(401, 403),
    tags=["institutions"],
)
async def list_all_institutions(
    admin: PlatformAdminDep, platform_session: PlatformSessionDep
) -> list[PlatformInstitutionOut]:
    """Super Admin only: every institution, with its number of active School Admins."""
    rows = await InstitutionService(platform_session).list_all_institutions()
    return [
        PlatformInstitutionOut(
            **InstitutionOut.model_validate(institution).model_dump(), school_admins=count
        )
        for institution, count in rows
    ]


@router.post(
    "/platform/institutions/{institution_id}/admins",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404),
    tags=["institutions"],
)
async def assign_school_admin(
    institution_id: uuid.UUID,
    body: AdminAssign,
    request: Request,
    admin: PlatformAdminDep,
    platform_session: PlatformSessionDep,
    settings: SettingsDep,
) -> None:
    """Super Admin only: make an existing account a School Admin of an institution."""
    user_id = await IdentityService(platform_session, settings).find_user_id_by_email(
        body.user_email
    )
    if user_id is None:
        raise NotFoundError("No active user with that email")
    await InstitutionService(platform_session).add_school_admin(institution_id, user_id, admin.id)
    await AuditService(platform_session).record(
        institution_id=institution_id,
        actor_user_id=admin.id,
        action="institution.school_admin_assigned",
        entity_type="user",
        entity_id=user_id,
        request_id=getattr(request.state, "request_id", None),
    )
    await platform_session.commit()


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


async def _user_id_for(email: str, session: SessionDep, settings: SettingsDep) -> uuid.UUID:
    user_id = await IdentityService(session, settings).find_user_id_by_email(email)
    if user_id is None:
        raise NotFoundError("No active user with that email")
    return user_id


@router.post(
    "/students",
    response_model=StudentOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409),
    tags=["people"],
)
async def create_student(
    body: StudentCreate, tenant: SchoolAdminDep, session: SessionDep, settings: SettingsDep
) -> StudentOut:
    """Register a student. With `user_email`, that account becomes an active member with
    the STUDENT role, so the student can record attendance from the mobile app."""
    user_id = None
    if body.user_email is not None:
        user_id = await _user_id_for(body.user_email, session, settings)
    student = await InstitutionService(session).create_student(
        tenant.institution_id,
        student_code=body.student_code,
        full_name=body.full_name,
        date_of_birth=body.date_of_birth,
        user_id=user_id,
        granted_by=tenant.user_id,
    )
    return StudentOut.model_validate(student)


@router.get("/students", response_model=list[StudentOut], responses=_errors, tags=["people"])
async def list_students(tenant: TenantDep, session: SessionDep) -> list[StudentOut]:
    if not tenant.has_any(InstitutionRole.SCHOOL_ADMIN, InstitutionRole.TEACHER):
        raise PermissionDeniedError("Only school admins and teachers can list students")
    students = await InstitutionService(session).list_students(tenant.institution_id)
    return [StudentOut.model_validate(s) for s in students]


@router.post(
    "/staff",
    response_model=StaffOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409),
    tags=["people"],
)
async def create_staff(
    body: StaffCreate, tenant: SchoolAdminDep, session: SessionDep, settings: SettingsDep
) -> StaffOut:
    """Register a staff member (teachers get the TEACHER role, others STAFF)."""
    user_id = await _user_id_for(body.user_email, session, settings)
    member = await InstitutionService(session).create_staff(
        tenant.institution_id,
        employee_code=body.employee_code,
        staff_type=body.staff_type,
        user_id=user_id,
        granted_by=tenant.user_id,
    )
    return StaffOut.model_validate(member)


@router.get("/staff", response_model=list[StaffOut], responses=_errors, tags=["people"])
async def list_staff(tenant: SchoolAdminDep, session: SessionDep) -> list[StaffOut]:
    members = await InstitutionService(session).list_staff(tenant.institution_id)
    return [StaffOut.model_validate(m) for m in members]


@router.post(
    "/guardians",
    response_model=GuardianOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409),
    tags=["guardians"],
)
async def create_guardian(
    body: GuardianCreate, tenant: SchoolAdminDep, session: SessionDep, settings: SettingsDep
) -> GuardianOut:
    """Register an existing account as a guardian (adds the GUARDIAN role)."""
    user_id = await _user_id_for(body.user_email, session, settings)
    guardian = await InstitutionService(session).create_guardian(
        tenant.institution_id, user_id=user_id, phone=body.phone, granted_by=tenant.user_id
    )
    return GuardianOut(
        id=guardian.id, user_id=guardian.user_id, phone=guardian.phone, student_ids=[]
    )


@router.get("/guardians", response_model=list[GuardianOut], responses=_errors, tags=["guardians"])
async def list_guardians(tenant: SchoolAdminDep, session: SessionDep) -> list[GuardianOut]:
    rows = await InstitutionService(session).list_guardians(tenant.institution_id)
    return [
        GuardianOut(id=g.id, user_id=g.user_id, phone=g.phone, student_ids=students)
        for g, students in rows
    ]


@router.post(
    "/guardians/{guardian_id}/students",
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409),
    tags=["guardians"],
)
async def link_guardian(
    guardian_id: uuid.UUID,
    body: GuardianLink,
    request: Request,
    tenant: SchoolAdminDep,
    session: SessionDep,
) -> dict[str, str]:
    """Authorize a guardian to follow a student's attendance. The authorization (who,
    when) is stored and audited, as required for minors' data."""
    await InstitutionService(session).link_guardian(
        tenant.institution_id,
        guardian_id=guardian_id,
        student_id=body.student_id,
        relationship=body.relationship,
        receives_alerts=body.receives_alerts,
        authorized_by=tenant.user_id,
    )
    await AuditService(session).record(
        institution_id=tenant.institution_id,
        actor_user_id=tenant.user_id,
        action="guardian.linked",
        entity_type="student_guardian",
        entity_id=f"{guardian_id}:{body.student_id}",
        changes=body.model_dump(mode="json"),
        request_id=getattr(request.state, "request_id", None),
    )
    await session.commit()
    return {"guardian_id": str(guardian_id), "student_id": str(body.student_id)}
