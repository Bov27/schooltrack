"""Geofence management and location validation."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, DomainError, NotFoundError
from app.modules.audit.service import AuditService
from app.modules.geolocation.repository import GeofenceRepository
from app.modules.geolocation.rules import GeoRules, LocationVerdict, evaluate_location
from app.modules.geolocation.schemas import GeofenceCreate, GeofenceUpdate, LocationCheck


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

    async def update_geofence(
        self,
        institution_id: uuid.UUID,
        geofence_id: uuid.UUID,
        body: GeofenceUpdate,
        actor_id: uuid.UUID,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        current = await self.repo.get(institution_id, geofence_id)
        if current is None:
            raise NotFoundError("Geofence not found")
        name = body.name.strip() if body.name is not None else current["name"]
        is_active = body.is_active if body.is_active is not None else current["is_active"]
        try:
            updated = await self.repo.update(
                institution_id, geofence_id, name=name, is_active=is_active
            )
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(f"This campus already has a geofence named '{name}'") from exc
        await AuditService(self.session).record(
            institution_id=institution_id,
            actor_user_id=actor_id,
            action="geofence.updated",
            entity_type="geofence",
            entity_id=geofence_id,
            changes={
                "name": [current["name"], name],
                "is_active": [current["is_active"], is_active],
            },
            request_id=request_id,
        )
        await self.session.commit()
        return updated

    async def delete_geofence(
        self,
        institution_id: uuid.UUID,
        geofence_id: uuid.UUID,
        actor_id: uuid.UUID,
        request_id: str | None = None,
    ) -> None:
        """Only never-used geofences can be deleted: attendance events reference the
        geofence that validated them, and that evidence must stay intact."""
        current = await self.repo.get(institution_id, geofence_id)
        if current is None:
            raise NotFoundError("Geofence not found")
        used = await self.repo.usage_count(institution_id, geofence_id)
        if used:
            await self.session.rollback()
            raise ConflictError(
                f"This geofence validated {used} attendance event(s) and cannot be deleted; "
                "deactivate it instead"
            )
        await self.repo.delete(institution_id, geofence_id)
        await AuditService(self.session).record(
            institution_id=institution_id,
            actor_user_id=actor_id,
            action="geofence.deleted",
            entity_type="geofence",
            entity_id=geofence_id,
            changes={"name": current["name"], "area_m2": current["area_m2"]},
            request_id=request_id,
        )
        await self.session.commit()

    async def list_geofences(
        self, institution_id: uuid.UUID, campus_id: uuid.UUID | None
    ) -> list[dict[str, Any]]:
        return await self.repo.list_for(institution_id, campus_id)

    async def check_location(
        self, institution_id: uuid.UUID, reading: LocationCheck, *, now: datetime | None = None
    ) -> LocationVerdict:
        """Evaluate a reading against the campus geofences. Nothing is stored."""
        return await self.evaluate(
            institution_id,
            campus_id=reading.campus_id,
            latitude=reading.latitude,
            longitude=reading.longitude,
            accuracy_m=reading.accuracy_m,
            captured_at=reading.captured_at,
            is_mock=reading.is_mock,
            now=now,
        )

    async def evaluate(
        self,
        institution_id: uuid.UUID,
        *,
        campus_id: uuid.UUID,
        latitude: float,
        longitude: float,
        accuracy_m: float,
        captured_at: datetime,
        is_mock: bool | None,
        now: datetime | None = None,
    ) -> LocationVerdict:
        """The single entry point for location decisions (also used by attendance)."""
        if not await self.repo.campus_exists(institution_id, campus_id):
            raise NotFoundError("Campus not found")
        match = await self.repo.nearest_active(institution_id, campus_id, latitude, longitude)
        return evaluate_location(
            rules=rules_from_settings(self.settings),
            now=now or datetime.now(UTC),
            captured_at=captured_at,
            accuracy_m=accuracy_m,
            is_mock=is_mock,
            match=match,
        )

    def _check_area(self, area_m2: float) -> None:
        low, high = self.settings.geofence_min_area_m2, self.settings.geofence_max_area_m2
        if not low <= area_m2 <= high:
            raise InvalidGeometryError(
                f"Geofence area {area_m2:,.0f} m² is outside the allowed range "
                f"{low:,.0f} to {high:,.0f} m²"
            )
