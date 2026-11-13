import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import SchoolAdminDep, SessionDep, SettingsDep, TenantDep
from app.api.errors import error_responses
from app.modules.geolocation.schemas import (
    GeofenceCreate,
    GeofenceOut,
    LocationCheck,
    LocationVerdictOut,
)
from app.modules.geolocation.service import GeolocationService

router = APIRouter(prefix="/geofences", tags=["geofences"])


@router.post(
    "",
    response_model=GeofenceOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409, 422),
)
async def create_geofence(
    body: GeofenceCreate, tenant: SchoolAdminDep, session: SessionDep, settings: SettingsDep
) -> GeofenceOut:
    """Create an authorized area for a campus, from a GeoJSON polygon or from a centre
    and radius (the server stores a 64-sided polygon approximating the circle)."""
    geofence = await GeolocationService(session, settings).create_geofence(
        tenant.institution_id, body, tenant.user_id
    )
    return GeofenceOut(**geofence)


@router.get("", response_model=list[GeofenceOut], responses=error_responses(401, 403))
async def list_geofences(
    tenant: TenantDep,
    session: SessionDep,
    settings: SettingsDep,
    campus_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[GeofenceOut]:
    geofences = await GeolocationService(session, settings).list_geofences(
        tenant.institution_id, campus_id
    )
    return [GeofenceOut(**g) for g in geofences]


@router.post(
    "/check",
    response_model=LocationVerdictOut,
    responses=error_responses(401, 403, 404),
)
async def check_location(
    body: LocationCheck, tenant: TenantDep, session: SessionDep, settings: SettingsDep
) -> LocationVerdictOut:
    """Dry run: how would this reading be judged? The location is **not stored**.
    Used by the admin dashboard to test geofences and by the attendance engine."""
    verdict = await GeolocationService(session, settings).check_location(
        tenant.institution_id, body
    )
    return LocationVerdictOut(
        verdict=verdict.verdict,
        geofence_result=verdict.geofence_result,
        reasons=verdict.reasons,
        geofence_id=verdict.geofence_id,
        distance_m=None if verdict.distance_m is None else round(verdict.distance_m, 1),
    )
