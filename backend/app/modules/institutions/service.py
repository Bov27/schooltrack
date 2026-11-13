"""Institutions, memberships and campuses.

Tenant-scoped methods assume the caller has already set the tenant context
(api.deps.get_tenant); RLS guarantees they cannot touch another institution even if
a query forgets to filter. Platform methods run on the platform session.
"""

import enum
import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.infrastructure.orm import set_current_user
from app.modules.institutions.models import (
    Campus,
    Guardian,
    Institution,
    InstitutionMembership,
    InstitutionRole,
    MembershipStatus,
    Staff,
    StaffType,
    Student,
    StudentGuardian,
    UserRole,
)


class SubjectKind(enum.StrEnum):
    STUDENT = "STUDENT"
    STAFF = "STAFF"


@dataclass(frozen=True, slots=True)
class Subject:
    """A person whose attendance is recorded."""

    kind: SubjectKind
    id: uuid.UUID


@dataclass(frozen=True, slots=True)
class MembershipSummary:
    institution_id: uuid.UUID
    institution_name: str
    roles: list[InstitutionRole] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ActiveMembership:
    institution_id: uuid.UUID
    roles: frozenset[InstitutionRole]


class InstitutionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ---- queries with only the user context ------------------------------------
    async def memberships_for(self, user_id: uuid.UUID) -> list[MembershipSummary]:
        await set_current_user(self.session, user_id)
        rows = (
            await self.session.execute(
                select(Institution.id, Institution.name, UserRole.role)
                .join(InstitutionMembership, InstitutionMembership.institution_id == Institution.id)
                .outerjoin(
                    UserRole,
                    (UserRole.institution_id == InstitutionMembership.institution_id)
                    & (UserRole.user_id == InstitutionMembership.user_id),
                )
                .where(
                    InstitutionMembership.user_id == user_id,
                    InstitutionMembership.status == MembershipStatus.ACTIVE,
                    Institution.is_active.is_(True),
                )
                .order_by(Institution.name, UserRole.role)
            )
        ).all()
        grouped: dict[uuid.UUID, MembershipSummary] = {}
        for institution_id, name, role in rows:
            summary = grouped.setdefault(institution_id, MembershipSummary(institution_id, name))
            if role is not None:
                summary.roles.append(role)
        return list(grouped.values())

    async def active_membership(
        self, user_id: uuid.UUID, institution_id: uuid.UUID | None
    ) -> ActiveMembership | None:
        """The user's active membership in `institution_id`, or, when it is None, their
        only active membership. Returns None when there is no unambiguous match."""
        memberships = await self.memberships_for(user_id)
        if institution_id is None:
            if len(memberships) != 1:
                return None
            chosen = memberships[0]
        else:
            matches = [m for m in memberships if m.institution_id == institution_id]
            if not matches:
                return None
            chosen = matches[0]
        return ActiveMembership(chosen.institution_id, frozenset(chosen.roles))

    async def list_my_institutions(self, user_id: uuid.UUID) -> list[Institution]:
        await set_current_user(self.session, user_id)
        result = await self.session.scalars(
            select(Institution).where(Institution.is_active.is_(True)).order_by(Institution.name)
        )
        return list(result)

    # ---- tenant-scoped (tenant context already set) ------------------------------
    async def list_campuses(self, institution_id: uuid.UUID) -> list[Campus]:
        result = await self.session.scalars(
            select(Campus).where(Campus.institution_id == institution_id).order_by(Campus.name)
        )
        return list(result)

    async def create_campus(
        self,
        institution_id: uuid.UUID,
        *,
        name: str,
        address: str | None,
        timezone: str | None,
    ) -> Campus:
        campus = Campus(
            institution_id=institution_id, name=name.strip(), address=address, timezone=timezone
        )
        self.session.add(campus)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(f"A campus named '{campus.name}' already exists") from exc
        await self.session.refresh(campus)
        await self.session.commit()
        return campus

    # ---- platform operations (platform session, BYPASSRLS) -----------------------
    async def create_institution(
        self,
        *,
        name: str,
        slug: str,
        timezone: str,
        admin_user_id: uuid.UUID | None,
        granted_by: uuid.UUID,
    ) -> Institution:
        institution = Institution(name=name.strip(), slug=slug, timezone=timezone)
        self.session.add(institution)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(f"An institution with slug '{slug}' already exists") from exc

        if admin_user_id is not None:
            self.session.add(
                InstitutionMembership(
                    institution_id=institution.id,
                    user_id=admin_user_id,
                    status=MembershipStatus.ACTIVE,
                )
            )
            await self.session.flush()
            self.session.add(
                UserRole(
                    institution_id=institution.id,
                    user_id=admin_user_id,
                    role=InstitutionRole.SCHOOL_ADMIN,
                    granted_by=granted_by,
                )
            )
        await self.session.flush()
        await self.session.refresh(institution)
        await self.session.commit()
        return institution

    async def list_all_institutions(self) -> list[tuple[Institution, int]]:
        """Platform view: every institution with its number of active School Admins."""
        admins = (
            select(func.count())
            .select_from(UserRole)
            .join(
                InstitutionMembership,
                (InstitutionMembership.institution_id == UserRole.institution_id)
                & (InstitutionMembership.user_id == UserRole.user_id),
            )
            .where(
                UserRole.institution_id == Institution.id,
                UserRole.role == InstitutionRole.SCHOOL_ADMIN,
                InstitutionMembership.status == MembershipStatus.ACTIVE,
            )
            .scalar_subquery()
        )
        query = select(Institution, admins).order_by(Institution.name)
        rows = (await self.session.execute(query)).all()
        return [(institution, int(count)) for institution, count in rows]

    async def add_school_admin(
        self, institution_id: uuid.UUID, user_id: uuid.UUID, granted_by: uuid.UUID
    ) -> None:
        """Platform operation: make a user an active School Admin (idempotent)."""
        await self.get_institution(institution_id)
        await self.session.execute(
            pg_insert(InstitutionMembership)
            .values(institution_id=institution_id, user_id=user_id, status=MembershipStatus.ACTIVE)
            .on_conflict_do_update(
                index_elements=["institution_id", "user_id"],
                set_={"status": MembershipStatus.ACTIVE},
            )
        )
        await self.session.execute(
            pg_insert(UserRole)
            .values(
                institution_id=institution_id,
                user_id=user_id,
                role=InstitutionRole.SCHOOL_ADMIN,
                granted_by=granted_by,
            )
            .on_conflict_do_nothing()
        )

    async def get_institution(self, institution_id: uuid.UUID) -> Institution:
        institution = await self.session.get(Institution, institution_id)
        if institution is None:
            raise NotFoundError("Institution not found")
        return institution

    # ---- people (tenant context already set) --------------------------------------
    async def _ensure_member_with_role(
        self,
        institution_id: uuid.UUID,
        user_id: uuid.UUID,
        role: InstitutionRole,
        granted_by: uuid.UUID,
    ) -> None:
        await self.session.execute(
            pg_insert(InstitutionMembership)
            .values(institution_id=institution_id, user_id=user_id, status=MembershipStatus.ACTIVE)
            .on_conflict_do_nothing(index_elements=["institution_id", "user_id"])
        )
        await self.session.execute(
            pg_insert(UserRole)
            .values(
                institution_id=institution_id, user_id=user_id, role=role, granted_by=granted_by
            )
            .on_conflict_do_nothing()
        )

    async def create_student(
        self,
        institution_id: uuid.UUID,
        *,
        student_code: str,
        full_name: str,
        date_of_birth: date | None,
        user_id: uuid.UUID | None,
        granted_by: uuid.UUID,
    ) -> Student:
        if user_id is not None:
            await self._ensure_member_with_role(
                institution_id, user_id, InstitutionRole.STUDENT, granted_by
            )
        student = Student(
            institution_id=institution_id,
            student_code=student_code.strip(),
            full_name=full_name.strip(),
            date_of_birth=date_of_birth,
            user_id=user_id,
        )
        self.session.add(student)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("A student with that code or account already exists") from exc
        await self.session.refresh(student)
        await self.session.commit()
        return student

    async def list_students(self, institution_id: uuid.UUID) -> list[Student]:
        result = await self.session.scalars(
            select(Student)
            .where(Student.institution_id == institution_id)
            .order_by(Student.full_name)
        )
        return list(result)

    async def create_staff(
        self,
        institution_id: uuid.UUID,
        *,
        employee_code: str,
        staff_type: StaffType,
        user_id: uuid.UUID,
        granted_by: uuid.UUID,
    ) -> Staff:
        role = InstitutionRole.TEACHER if staff_type is StaffType.TEACHER else InstitutionRole.STAFF
        await self._ensure_member_with_role(institution_id, user_id, role, granted_by)
        member = Staff(
            institution_id=institution_id,
            employee_code=employee_code.strip(),
            staff_type=staff_type,
            user_id=user_id,
        )
        self.session.add(member)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("A staff member with that code or account already exists") from exc
        await self.session.refresh(member)
        await self.session.commit()
        return member

    async def list_staff(self, institution_id: uuid.UUID) -> list[Staff]:
        result = await self.session.scalars(
            select(Staff)
            .where(Staff.institution_id == institution_id)
            .order_by(Staff.employee_code)
        )
        return list(result)

    async def subjects_for_user(
        self, institution_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Subject]:
        """The active student and/or staff records linked to this user account."""
        subjects: list[Subject] = []
        student_id = await self.session.scalar(
            select(Student.id).where(
                Student.institution_id == institution_id,
                Student.user_id == user_id,
                Student.is_active.is_(True),
            )
        )
        if student_id is not None:
            subjects.append(Subject(SubjectKind.STUDENT, student_id))
        staff_id = await self.session.scalar(
            select(Staff.id).where(
                Staff.institution_id == institution_id,
                Staff.user_id == user_id,
                Staff.is_active.is_(True),
            )
        )
        if staff_id is not None:
            subjects.append(Subject(SubjectKind.STAFF, staff_id))
        return subjects

    async def campus_exists(self, institution_id: uuid.UUID, campus_id: uuid.UUID) -> bool:
        found = await self.session.scalar(
            select(Campus.id).where(Campus.institution_id == institution_id, Campus.id == campus_id)
        )
        return found is not None

    async def subject_exists(self, institution_id: uuid.UUID, subject: Subject) -> bool:
        model = Student if subject.kind is SubjectKind.STUDENT else Staff
        found = await self.session.scalar(
            select(model.id).where(
                model.institution_id == institution_id,
                model.id == subject.id,
                model.is_active.is_(True),
            )
        )
        return found is not None

    # ---- guardians (tenant context already set) -----------------------------------
    async def create_guardian(
        self,
        institution_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        phone: str | None,
        granted_by: uuid.UUID,
    ) -> Guardian:
        await self._ensure_member_with_role(
            institution_id, user_id, InstitutionRole.GUARDIAN, granted_by
        )
        guardian = Guardian(institution_id=institution_id, user_id=user_id, phone=phone)
        self.session.add(guardian)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("That account is already a guardian in this institution") from exc
        await self.session.refresh(guardian)
        await self.session.commit()
        return guardian

    async def link_guardian(
        self,
        institution_id: uuid.UUID,
        *,
        guardian_id: uuid.UUID,
        student_id: uuid.UUID,
        relationship: str,
        receives_alerts: bool,
        authorized_by: uuid.UUID,
    ) -> StudentGuardian:
        guardian = await self.session.scalar(
            select(Guardian.id).where(
                Guardian.institution_id == institution_id, Guardian.id == guardian_id
            )
        )
        if guardian is None or not await self.subject_exists(
            institution_id, Subject(SubjectKind.STUDENT, student_id)
        ):
            raise NotFoundError("Guardian or student not found")
        link = StudentGuardian(
            institution_id=institution_id,
            student_id=student_id,
            guardian_id=guardian_id,
            relationship=relationship.strip(),
            receives_alerts=receives_alerts,
            authorized_by=authorized_by,
        )
        self.session.add(link)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError("This guardian is already linked to the student") from exc
        return link  # the caller commits, together with its audit entry

    async def list_guardians(
        self, institution_id: uuid.UUID
    ) -> list[tuple[Guardian, list[uuid.UUID]]]:
        guardians = list(
            await self.session.scalars(
                select(Guardian)
                .where(Guardian.institution_id == institution_id)
                .order_by(Guardian.created_at)
            )
        )
        links = (
            await self.session.execute(
                select(StudentGuardian.guardian_id, StudentGuardian.student_id).where(
                    StudentGuardian.institution_id == institution_id
                )
            )
        ).all()
        by_guardian: dict[uuid.UUID, list[uuid.UUID]] = {}
        for guardian_id, student_id in links:
            by_guardian.setdefault(guardian_id, []).append(student_id)
        return [(g, by_guardian.get(g.id, [])) for g in guardians]

    async def guarded_students(
        self, institution_id: uuid.UUID, user_id: uuid.UUID
    ) -> list[Student]:
        """Students this user is an authorized guardian of, in this institution."""
        result = await self.session.scalars(
            select(Student)
            .join(
                StudentGuardian,
                (StudentGuardian.institution_id == Student.institution_id)
                & (StudentGuardian.student_id == Student.id),
            )
            .join(
                Guardian,
                (Guardian.institution_id == StudentGuardian.institution_id)
                & (Guardian.id == StudentGuardian.guardian_id),
            )
            .where(Student.institution_id == institution_id, Guardian.user_id == user_id)
            .order_by(Student.full_name)
        )
        return list(result)
