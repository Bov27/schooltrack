"""Operational commands. They run with the owner connection (MIGRATIONS_DATABASE_URL),
because creating the first platform administrator cannot go through the API.

    python -m app.cli create-platform-admin --email admin@example.test --name "Platform Admin"

The password is read from SCHOOLTRACK_ADMIN_PASSWORD or prompted for.
"""

import argparse
import getpass
import os
import sys

import psycopg

from app.core.security import hash_password
from app.modules.identity.service import normalize_email

MIN_PASSWORD_LENGTH = 12


def _owner_dsn() -> str:
    url = os.environ.get("MIGRATIONS_DATABASE_URL")
    if not url:
        sys.exit("MIGRATIONS_DATABASE_URL (owner role) must be set")
    # SQLAlchemy URL -> libpq URL
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _read_password() -> str:
    password = os.environ.get("SCHOOLTRACK_ADMIN_PASSWORD") or getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password must have at least {MIN_PASSWORD_LENGTH} characters")
    return password


def create_platform_admin(email: str, name: str) -> None:
    password_hash = hash_password(_read_password())
    with psycopg.connect(_owner_dsn()) as conn:
        user_id = conn.execute(
            """
            INSERT INTO users (email, full_name, password_hash)
            VALUES (%s, %s, %s)
            ON CONFLICT (email) DO UPDATE
                SET password_hash = EXCLUDED.password_hash, updated_at = now()
            RETURNING id
            """,
            (normalize_email(email), name, password_hash),
        ).fetchone()
        if user_id is None:  # pragma: no cover - RETURNING always yields a row here
            sys.exit("Could not create the user")
        conn.execute(
            "INSERT INTO platform_admins (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (user_id[0],),
        )
    print(f"Platform admin ready: {normalize_email(email)} ({user_id[0]})")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("create-platform-admin", help="Create or reset a Super Admin")
    admin.add_argument("--email", required=True)
    admin.add_argument("--name", required=True)
    args = parser.parse_args(argv)

    if args.command == "create-platform-admin":
        create_platform_admin(args.email, args.name)


if __name__ == "__main__":
    main()
