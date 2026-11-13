"""Alembic environment. Migrations run with the owner role, never with the API runtime role."""

import os

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config

# SQLAlchemy models will provide metadata from Week 2 for autogenerate support.
target_metadata = None


def _database_url() -> str:
    url = os.environ.get("MIGRATIONS_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Set MIGRATIONS_DATABASE_URL (owner role) to run migrations")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_database_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # psycopg 3 supports synchronous connections too, so one driver serves the API and migrations.
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
