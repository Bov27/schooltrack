import enum
import uuid
from datetime import date, datetime

from sqlalchemy import ForeignKey, ForeignKeyConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.orm import Base, pg_enum


class InstitutionRole(enum.StrEnum):
    SCHOOL_ADMIN = "SCHOOL_ADMIN"
    TEACHER = "TEACHER"
    STUDENT = "STUDENT"
    STAFF = "STAFF"
    GUARDIAN = "GUARDIAN"


class MembershipStatus(enum.StrEnum):
    INVITED = "INVITED"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str]
    slug: Mapped[str]
    country: Mapped[str] = mapped_column(server_default=text("'CO'"))
    timezone: Mapped[str] = mapped_column(server_default=text("'America/Bogota'"))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class InstitutionMembership(Base):
    __tablename__ = "institution_memberships"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    status: Mapped[MembershipStatus] = mapped_column(
        pg_enum(MembershipStatus, "membership_status"), server_default=text("'INVITED'")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        ForeignKeyConstraint(
            ["institution_id", "user_id"],
            ["institution_memberships.institution_id", "institution_memberships.user_id"],
        ),
    )

    institution_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    role: Mapped[InstitutionRole] = mapped_column(
        pg_enum(InstitutionRole, "institution_role"), primary_key=True
    )
    granted_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
    granted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class Campus(Base):
    __tablename__ = "campuses"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"))
    name: Mapped[str]
    address: Mapped[str | None]
    timezone: Mapped[str | None]
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class StaffType(enum.StrEnum):
    TEACHER = "TEACHER"
    ADMINISTRATIVE = "ADMINISTRATIVE"
    SUPPORT = "SUPPORT"


class Student(Base):
    __tablename__ = "students"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"))
    user_id: Mapped[uuid.UUID | None]
    student_code: Mapped[str]
    full_name: Mapped[str]
    date_of_birth: Mapped[date | None]
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))


class Staff(Base):
    __tablename__ = "staff"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, server_default=text("gen_random_uuid()")
    )
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"))
    user_id: Mapped[uuid.UUID]
    employee_code: Mapped[str]
    staff_type: Mapped[StaffType] = mapped_column(pg_enum(StaffType, "staff_type"))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(server_default=text("now()"))
