"""Geofences: authorized campus areas as PostGIS geography polygons.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-13
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "schooltrack_app"


def upgrade() -> None:
    # GEOGRAPHY measures on the WGS84 ellipsoid, so areas and distances are in metres
    # without choosing a projection (ADR-003).
    op.execute(
        """
        CREATE TABLE geofences (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            institution_id  uuid NOT NULL,
            campus_id       uuid NOT NULL,
            name            text NOT NULL CHECK (length(btrim(name)) > 0),
            area            geography(POLYGON, 4326) NOT NULL
                            CHECK (ST_IsValid(area::geometry) AND ST_Area(area) > 0),
            is_active       boolean NOT NULL DEFAULT true,
            created_at      timestamptz NOT NULL DEFAULT now(),
            created_by      uuid REFERENCES users(id),
            UNIQUE (institution_id, id),
            UNIQUE (institution_id, campus_id, name),
            FOREIGN KEY (institution_id, campus_id) REFERENCES campuses (institution_id, id)
        )
        """
    )
    op.execute("CREATE INDEX geofences_area_gist ON geofences USING GIST (area)")
    op.execute(
        "CREATE INDEX geofences_campus_active_idx ON geofences (institution_id, campus_id) "
        "WHERE is_active"
    )

    op.execute("ALTER TABLE geofences ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE geofences FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON geofences "
        "USING (institution_id = app_current_institution_id()) "
        "WITH CHECK (institution_id = app_current_institution_id())"
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE ON geofences TO {APP_ROLE}")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS geofences")
