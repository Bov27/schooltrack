import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import SchoolAdminDep, SessionDep, SettingsDep, TenantDep
from app.api.errors import error_responses
from app.modules.geolocation.schemas import (
    GeofenceCreate,
    GeofenceOut,
    GeofenceUpdate,
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


@router.patch(
    "/{geofence_id}", response_model=GeofenceOut, responses=error_responses(401, 403, 404, 409)
)
async def update_geofence(
    geofence_id: uuid.UUID,
    body: GeofenceUpdate,
    request: Request,
    tenant: SchoolAdminDep,
    session: SessionDep,
    settings: SettingsDep,
) -> GeofenceOut:
    """Rename, activate or deactivate. Inactive geofences are ignored by validation but
    kept, so past events still point at the area that validated them. Audited."""
    geofence = await GeolocationService(session, settings).update_geofence(
        tenant.institution_id,
        geofence_id,
        body,
        tenant.user_id,
        getattr(request.state, "request_id", None),
    )
    return GeofenceOut(**geofence)


@router.delete(
    "/{geofence_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409),
)
async def delete_geofence(
    geofence_id: uuid.UUID,
    request: Request,
    tenant: SchoolAdminDep,
    session: SessionDep,
    settings: SettingsDep,
) -> None:
    """Delete a geofence that never validated an event (409 otherwise: deactivate it)."""
    await GeolocationService(session, settings).delete_geofence(
        tenant.institution_id,
        geofence_id,
        tenant.user_id,
        getattr(request.state, "request_id", None),
    )


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
