"""Institutions, memberships and campuses.

Tenant-scoped methods assume the caller has already set the tenant context
(api.deps.get_tenant); RLS guarantees they cannot touch another institution even if
a query forgets to filter. Platform methods run on the platform session.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.infrastructure.orm import set_current_user
from app.modules.institutions.models import (
    Campus,
    Institution,
    InstitutionMembership,
    InstitutionRole,
    MembershipStatus,
    UserRole,
)


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

    async def get_institution(self, institution_id: uuid.UUID) -> Institution:
        institution = await self.session.get(Institution, institution_id)
        if institution is None:
            raise NotFoundError("Institution not found")
        return institution
