"""Allow School Admins to delete unused geofences.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Geofences referenced by attendance events stay protected by the foreign key from
    # attendance_events; the service refuses those deletions with a clear message first.
    op.execute("GRANT DELETE ON geofences TO schooltrack_app")


def downgrade() -> None:
    op.execute("REVOKE DELETE ON geofences FROM schooltrack_app")
