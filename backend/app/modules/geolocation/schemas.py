import uuid
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.modules.geolocation.rules import GeofenceResult, Reason, Verdict

Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]
MAX_RING_POSITIONS = 1000


class GeoJSONPolygon(BaseModel):
    """GeoJSON Polygon (RFC 7946) with a single exterior ring; positions are [lng, lat]."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["Polygon"]
    coordinates: list[list[tuple[Longitude, Latitude]]] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def _check_ring(self) -> Self:
        ring = self.coordinates[0]
        if len(ring) < 4:
            raise ValueError("A polygon ring needs at least 4 positions (3 corners + closing)")
        if len(ring) > MAX_RING_POSITIONS:
            raise ValueError(f"A polygon ring may have at most {MAX_RING_POSITIONS} positions")
        if ring[0] != ring[-1]:
            raise ValueError("The polygon ring must be closed (first position == last)")
        return self


class Point(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: Latitude
    longitude: Longitude


class GeofenceCreate(BaseModel):
    """Either `area` (a polygon) or `center` (+ optional `radius_m`), not both."""

    model_config = ConfigDict(extra="forbid")

    campus_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    area: GeoJSONPolygon | None = None
    center: Point | None = None
    radius_m: float | None = Field(default=None, gt=0, le=5_000)

    @model_validator(mode="after")
    def _one_shape(self) -> Self:
        if (self.area is None) == (self.center is None):
            raise ValueError("Provide exactly one of 'area' or 'center'")
        if self.area is not None and self.radius_m is not None:
            raise ValueError("'radius_m' only applies together with 'center'")
        return self


class GeofenceOut(BaseModel):
    id: uuid.UUID
    campus_id: uuid.UUID
    name: str
    is_active: bool
    area: dict[str, Any] = Field(description="GeoJSON Polygon")
    area_m2: float
    created_at: datetime


class LocationCheck(BaseModel):
    """A location reading as the mobile app captures it at the moment of an action."""

    model_config = ConfigDict(extra="forbid")

    campus_id: uuid.UUID
    latitude: Latitude
    longitude: Longitude
    accuracy_m: float = Field(ge=0, le=10_000, description="Horizontal accuracy reported by the OS")
    captured_at: AwareDatetime = Field(description="When the OS obtained the fix")
    is_mock: bool | None = Field(
        default=None, description="Mock-location flag where the platform reports it"
    )


class LocationVerdictOut(BaseModel):
    verdict: Verdict
    geofence_result: GeofenceResult
    reasons: list[Reason]
    geofence_id: uuid.UUID | None
    distance_m: float | None
