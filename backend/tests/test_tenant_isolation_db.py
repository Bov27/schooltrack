"""Tenant isolation at the database level, independent of application code.

These tests connect directly with the runtime role (schooltrack_app), the same way the
API does, and check that RLS and grants hold even for hand-written SQL.
"""

import os
import uuid
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

from tests.db_support import (
    Factory,
    requires_database,
)

pytestmark = [requires_database]


def _libpq(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


@pytest.fixture
def app_conn(owner_conn: psycopg.Connection[Any]) -> Iterator[psycopg.Connection[Any]]:
    with psycopg.connect(_libpq(os.environ["DATABASE_URL"])) as conn:
        yield conn


def _in_tenant(conn: psycopg.Connection[Any], institution_id: uuid.UUID) -> None:
    conn.execute(
        "SELECT set_config('app.current_institution_id', %s, true)", (str(institution_id),)
    )


def test_every_tenant_table_has_forced_rls_and_a_policy(
    owner_conn: psycopg.Connection[Any],
) -> None:
    rows = owner_conn.execute(
        """
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
               EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = c.oid) AS has_policy
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
        WHERE c.relkind = 'r'
          AND (c.relname = 'institutions'
               OR EXISTS (SELECT 1 FROM pg_attribute a
                          WHERE a.attrelid = c.oid AND a.attname = 'institution_id'
                            AND NOT a.attisdropped))
        """
    ).fetchall()
    assert rows, "expected tenant tables"
    unprotected = [name for name, rls, forced, policy in rows if not (rls and forced and policy)]
    assert unprotected == []


def test_runtime_role_cannot_bypass_rls(app_conn: psycopg.Connection[Any]) -> None:
    row = app_conn.execute(
        "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ).fetchone()
    assert row == (False, False)


def test_no_tenant_context_means_no_rows(
    app_conn: psycopg.Connection[Any], factory: Factory
) -> None:
    a = factory.institution("colegio-a")
    factory.campus(a, "Sede Norte")
    for table in ("institutions", "campuses", "institution_memberships", "user_roles"):
        count = app_conn.execute(f"SELECT count(*) FROM {table}").fetchone()  # noqa: S608
        assert count == (0,), table


def test_tenant_context_limits_reads_and_writes(
    app_conn: psycopg.Connection[Any], factory: Factory
) -> None:
    a, b = factory.institution("colegio-a"), factory.institution("colegio-b")
    factory.campus(a, "Sede Norte")
    campus_b = factory.campus(b, "Sede Sur")

    _in_tenant(app_conn, a)
    names = app_conn.execute("SELECT name FROM campuses").fetchall()
    assert names == [("Sede Norte",)]

    updated = app_conn.execute(
        "UPDATE campuses SET name = 'hacked' WHERE id = %s", (campus_b,)
    ).rowcount
    assert updated == 0

    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_conn.execute(
            "INSERT INTO campuses (institution_id, name) VALUES (%s, 'Infiltrada')", (b,)
        )


def test_tenant_context_does_not_outlive_the_transaction(
    app_conn: psycopg.Connection[Any], factory: Factory
) -> None:
    a = factory.institution("colegio-a")
    factory.campus(a, "Sede Norte")
    _in_tenant(app_conn, a)
    assert app_conn.execute("SELECT count(*) FROM campuses").fetchone() == (1,)
    app_conn.commit()
    assert app_conn.execute("SELECT count(*) FROM campuses").fetchone() == (0,)


def test_runtime_role_cannot_create_institutions_or_platform_admins(
    app_conn: psycopg.Connection[Any], factory: Factory
) -> None:
    user = factory.user("ana@colegio-a.test")
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_conn.execute("INSERT INTO institutions (name, slug) VALUES ('X', 'x')")
    app_conn.rollback()
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_conn.execute("INSERT INTO platform_admins (user_id) VALUES (%s)", (user,))
