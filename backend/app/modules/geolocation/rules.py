"""Location validation rules (ADR-003).

Pure functions with no I/O: the database answers the spatial question (which active
geofence is nearest, does it cover the point, how far is it) and this module turns
that answer plus the GPS metadata into a verdict. Keeping the decision here makes
every rule unit-testable and easy to review.

Verdicts:
    VALIDATED           every check passed
    FLAGGED_FOR_REVIEW  plausible but uncertain; a person should look at it
    REJECTED            a hard rule failed
"""

import enum
import uuid
from dataclasses import dataclass, field
from datetime import datetime


class GeofenceResult(enum.StrEnum):
    INSIDE = "INSIDE"
    OUTSIDE = "OUTSIDE"
    NOT_EVALUATED = "NOT_EVALUATED"


class Verdict(enum.StrEnum):
    VALIDATED = "VALIDATED"
    FLAGGED_FOR_REVIEW = "FLAGGED_FOR_REVIEW"
    REJECTED = "REJECTED"


class Reason(enum.StrEnum):
    # Hard: the event cannot be accepted.
    NO_ACTIVE_GEOFENCE = "NO_ACTIVE_GEOFENCE"
    GPS_ACCURACY_TOO_LOW = "GPS_ACCURACY_TOO_LOW"
    LOCATION_TOO_OLD = "LOCATION_TOO_OLD"
    LOCATION_IN_FUTURE = "LOCATION_IN_FUTURE"
    OUTSIDE_GEOFENCE = "OUTSIDE_GEOFENCE"
    # Soft: accepted for review only.
    BOUNDARY_UNCERTAIN = "BOUNDARY_UNCERTAIN"
    MOCK_LOCATION_REPORTED = "MOCK_LOCATION_REPORTED"


HARD_REASONS = frozenset(
    {
        Reason.NO_ACTIVE_GEOFENCE,
        Reason.GPS_ACCURACY_TOO_LOW,
        Reason.LOCATION_TOO_OLD,
        Reason.LOCATION_IN_FUTURE,
        Reason.OUTSIDE_GEOFENCE,
    }
)


@dataclass(frozen=True, slots=True)
class GeoRules:
    max_accuracy_m: float
    max_location_age_s: float
    clock_skew_tolerance_s: float


@dataclass(frozen=True, slots=True)
class GeofenceMatch:
    """The campus's nearest active geofence, as computed by PostGIS."""

    geofence_id: uuid.UUID
    covers: bool          # ST_Covers: boundary points count as inside
    distance_m: float     # 0 when covered


@dataclass(frozen=True, slots=True)
class LocationVerdict:
    verdict: Verdict
    geofence_result: GeofenceResult
    reasons: list[Reason] = field(default_factory=list)
    geofence_id: uuid.UUID | None = None
    distance_m: float | None = None


def evaluate_location(
    *,
    rules: GeoRules,
    now: datetime,
    captured_at: datetime,
    accuracy_m: float,
    is_mock: bool | None,
    match: GeofenceMatch | None,
) -> LocationVerdict:
    reasons: list[Reason] = []

    age_s = (now - captured_at).total_seconds()
    if age_s < -rules.clock_skew_tolerance_s:
        reasons.append(Reason.LOCATION_IN_FUTURE)
    elif age_s > rules.max_location_age_s:
        reasons.append(Reason.LOCATION_TOO_OLD)

    if accuracy_m > rules.max_accuracy_m:
        reasons.append(Reason.GPS_ACCURACY_TOO_LOW)

    if is_mock:
        reasons.append(Reason.MOCK_LOCATION_REPORTED)

    if match is None:
        reasons.append(Reason.NO_ACTIVE_GEOFENCE)
        result = GeofenceResult.NOT_EVALUATED
    elif match.covers:
        result = GeofenceResult.INSIDE
    else:
        result = GeofenceResult.OUTSIDE
        # The true position lies (with the reported confidence) within accuracy_m of the
        # reading. If that circle reaches the geofence the person may well be inside.
        if match.distance_m <= accuracy_m:
            reasons.append(Reason.BOUNDARY_UNCERTAIN)
        else:
            reasons.append(Reason.OUTSIDE_GEOFENCE)

    if any(r in HARD_REASONS for r in reasons):
        verdict = Verdict.REJECTED
    elif reasons:
        verdict = Verdict.FLAGGED_FOR_REVIEW
    else:
        verdict = Verdict.VALIDATED

    return LocationVerdict(
        verdict=verdict,
        geofence_result=result,
        reasons=reasons,
        geofence_id=match.geofence_id if match else None,
        distance_m=match.distance_m if match else None,
    )
