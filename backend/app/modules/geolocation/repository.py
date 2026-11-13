"""PostGIS queries. Geography columns are handled in SQL (text()) rather than through
an ORM type, which keeps the spatial operations explicit and reviewable.

All queries run in the request's transaction, with the tenant context already set, so
RLS limits them to the current institution in addition to the explicit filters.
"""

import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.geolocation.rules import GeofenceMatch

_POINT = "ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography"
_FROM_GEOJSON = "ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326)::geography"
# quad_segs=16 -> a 64-sided polygon: area within 0.2 % of the true circle.
_FROM_CIRCLE = f"ST_Buffer({_POINT}, :radius, 'quad_segs=16')"

_RETURNING = (
    "id, campus_id, name, is_active, created_at, "
    "ST_AsGeoJSON(area)::text AS area_geojson, ST_Area(area) AS area_m2"
)


@dataclass(frozen=True, slots=True)
class ShapeCheck:
    is_valid: bool
    reason: str
    area_m2: float


def _row_to_dict(row: Any) -> dict[str, Any]:
    data = dict(row._mapping)
    data["area"] = json.loads(data.pop("area_geojson"))
    return data


class GeofenceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def campus_exists(self, institution_id: uuid.UUID, campus_id: uuid.UUID) -> bool:
        found = await self.session.scalar(
            text("SELECT 1 FROM campuses WHERE institution_id = :inst AND id = :campus"),
            {"inst": institution_id, "campus": campus_id},
        )
        return found is not None

    async def inspect_polygon(self, geojson: str) -> ShapeCheck:
        row = (
            await self.session.execute(
                text(
                    "SELECT ST_IsValid(g::geometry) AS ok, ST_IsValidReason(g::geometry) AS why, "
                    f"ST_Area(g) AS area FROM (SELECT {_FROM_GEOJSON} AS g) s"
                ),
                {"geojson": geojson},
            )
        ).one()
        return ShapeCheck(bool(row.ok), str(row.why), float(row.area))

    async def circle_area(self, lat: float, lng: float, radius: float) -> float:
        area = await self.session.scalar(
            text(f"SELECT ST_Area({_FROM_CIRCLE})"), {"lat": lat, "lng": lng, "radius": radius}
        )
        return float(area)

    async def insert_polygon(
        self,
        *,
        institution_id: uuid.UUID,
        campus_id: uuid.UUID,
        name: str,
        geojson: str,
        created_by: uuid.UUID,
    ) -> dict[str, Any]:
        row = (
            await self.session.execute(
                text(
                    "INSERT INTO geofences (institution_id, campus_id, name, area, created_by) "
                    f"VALUES (:inst, :campus, :name, {_FROM_GEOJSON}, :by) RETURNING {_RETURNING}"
                ),
                {
                    "inst": institution_id,
                    "campus": campus_id,
                    "name": name,
                    "geojson": geojson,
                    "by": created_by,
                },
            )
        ).one()
        return _row_to_dict(row)

    async def insert_circle(
        self,
        *,
        institution_id: uuid.UUID,
        campus_id: uuid.UUID,
        name: str,
        lat: float,
        lng: float,
        radius: float,
        created_by: uuid.UUID,
    ) -> dict[str, Any]:
        row = (
            await self.session.execute(
                text(
                    "INSERT INTO geofences (institution_id, campus_id, name, area, created_by) "
                    f"VALUES (:inst, :campus, :name, {_FROM_CIRCLE}, :by) RETURNING {_RETURNING}"
                ),
                {
                    "inst": institution_id,
                    "campus": campus_id,
                    "name": name,
                    "lat": lat,
                    "lng": lng,
                    "radius": radius,
                    "by": created_by,
                },
            )
        ).one()
        return _row_to_dict(row)

    async def list_for(
        self, institution_id: uuid.UUID, campus_id: uuid.UUID | None
    ) -> list[dict[str, Any]]:
        rows = (
            await self.session.execute(
                text(
                    f"SELECT {_RETURNING} FROM geofences "
                    "WHERE institution_id = :inst "
                    "AND (CAST(:campus AS uuid) IS NULL OR campus_id = :campus) "
                    "ORDER BY name"
                ),
                {"inst": institution_id, "campus": campus_id},
            )
        ).all()
        return [_row_to_dict(r) for r in rows]

    async def nearest_active(
        self, institution_id: uuid.UUID, campus_id: uuid.UUID, lat: float, lng: float
    ) -> GeofenceMatch | None:
        """The campus's active geofence closest to the point (distance 0 if inside).
        ST_Covers rather than ST_Contains so a point exactly on the edge counts as inside."""
        row = (
            await self.session.execute(
                text(
                    "SELECT g.id, ST_Covers(g.area, p.pt) AS covers, "
                    "ST_Distance(g.area, p.pt) AS distance_m "
                    f"FROM geofences g, (SELECT {_POINT} AS pt) p "
                    "WHERE g.institution_id = :inst AND g.campus_id = :campus AND g.is_active "
                    "ORDER BY ST_Distance(g.area, p.pt) LIMIT 1"
                ),
                {"inst": institution_id, "campus": campus_id, "lat": lat, "lng": lng},
            )
        ).one_or_none()
        if row is None:
            return None
        return GeofenceMatch(row.id, covers=bool(row.covers), distance_m=float(row.distance_m))
