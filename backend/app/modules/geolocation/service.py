"""Geofence management and location validation."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.modules.geolocation.repository import GeofenceRepository
from app.modules.geolocation.rules import GeoRules, LocationVerdict, evaluate_location
from app.modules.geolocation.schemas import GeofenceCreate, LocationCheck


class InvalidGeometryError(DomainError):
    status_code = 422


def rules_from_settings(settings: Settings) -> GeoRules:
    return GeoRules(
        max_accuracy_m=settings.gps_max_accuracy_m,
        max_location_age_s=settings.location_max_age_s,
        clock_skew_tolerance_s=settings.clock_skew_tolerance_s,
    )


class GeolocationService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repo = GeofenceRepository(session)

    async def create_geofence(
        self, institution_id: uuid.UUID, body: GeofenceCreate, created_by: uuid.UUID
    ) -> dict[str, Any]:
        if not await self.repo.campus_exists(institution_id, body.campus_id):
            raise NotFoundError("Campus not found")

        name = body.name.strip()
        if body.area is not None:
            geojson = body.area.model_dump_json()
            shape = await self.repo.inspect_polygon(geojson)
            if not shape.is_valid:
                raise InvalidGeometryError(f"Invalid polygon: {shape.reason}")
            self._check_area(shape.area_m2)
            insert = self.repo.insert_polygon(
                institution_id=institution_id,
                campus_id=body.campus_id,
                name=name,
                geojson=geojson,
                created_by=created_by,
            )
        else:
            assert body.center is not None  # guaranteed by GeofenceCreate validation  # noqa: S101
            radius = body.radius_m or self.settings.geofence_default_radius_m
            lat, lng = body.center.latitude, body.center.longitude
            self._check_area(await self.repo.circle_area(lat, lng, radius))
            insert = self.repo.insert_circle(
                institution_id=institution_id,
                campus_id=body.campus_id,
                name=name,
                lat=lat,
                lng=lng,
                radius=radius,
                created_by=created_by,
            )

        try:
            geofence = await insert
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(f"This campus already has a geofence named '{name}'") from exc
        await self.session.commit()
        return geofence

    async def list_geofences(
        self, institution_id: uuid.UUID, campus_id: uuid.UUID | None
    ) -> list[dict[str, Any]]:
        return await self.repo.list_for(institution_id, campus_id)

    async def check_location(
        self, institution_id: uuid.UUID, reading: LocationCheck, *, now: datetime | None = None
    ) -> LocationVerdict:
        """Evaluate a reading against the campus geofences. Nothing is stored."""
        if not await self.repo.campus_exists(institution_id, reading.campus_id):
            raise NotFoundError("Campus not found")
        match = await self.repo.nearest_active(
            institution_id, reading.campus_id, reading.latitude, reading.longitude
        )
        return evaluate_location(
            rules=rules_from_settings(self.settings),
            now=now or datetime.now(UTC),
            captured_at=reading.captured_at,
            accuracy_m=reading.accuracy_m,
            is_mock=reading.is_mock,
            match=match,
        )

    def _check_area(self, area_m2: float) -> None:
        low, high = self.settings.geofence_min_area_m2, self.settings.geofence_max_area_m2
        if not low <= area_m2 <= high:
            raise InvalidGeometryError(
                f"Geofence area {area_m2:,.0f} m² is outside the allowed range "
                f"{low:,.0f} to {high:,.0f} m²"
            )
