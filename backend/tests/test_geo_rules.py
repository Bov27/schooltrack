"""Unit tests for the location decision rules (no database)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.modules.geolocation.rules import (
    GeofenceMatch,
    GeofenceResult,
    GeoRules,
    Reason,
    Verdict,
    evaluate_location,
)

RULES = GeoRules(max_accuracy_m=30, max_location_age_s=30, clock_skew_tolerance_s=5)
NOW = datetime(2027, 2, 1, 7, 0, tzinfo=UTC)
FENCE = uuid.uuid4()


def check(
    *,
    age_s: float = 2,
    accuracy_m: float = 10,
    is_mock: bool | None = False,
    match: GeofenceMatch | None = GeofenceMatch(FENCE, covers=True, distance_m=0),  # noqa: B008
) -> tuple[Verdict, GeofenceResult, list[Reason]]:
    verdict = evaluate_location(
        rules=RULES,
        now=NOW,
        captured_at=NOW - timedelta(seconds=age_s),
        accuracy_m=accuracy_m,
        is_mock=is_mock,
        match=match,
    )
    return verdict.verdict, verdict.geofence_result, verdict.reasons


def test_good_reading_inside_is_validated() -> None:
    assert check() == (Verdict.VALIDATED, GeofenceResult.INSIDE, [])


def test_reading_at_the_thresholds_is_still_valid() -> None:
    assert check(age_s=30, accuracy_m=30)[0] is Verdict.VALIDATED


def test_inaccurate_reading_is_rejected_even_inside() -> None:
    assert check(accuracy_m=30.1) == (
        Verdict.REJECTED,
        GeofenceResult.INSIDE,
        [Reason.GPS_ACCURACY_TOO_LOW],
    )


def test_stale_reading_is_rejected() -> None:
    assert check(age_s=31)[2] == [Reason.LOCATION_TOO_OLD]


def test_small_clock_skew_is_tolerated_but_future_readings_are_rejected() -> None:
    assert check(age_s=-4)[0] is Verdict.VALIDATED
    assert check(age_s=-6)[2] == [Reason.LOCATION_IN_FUTURE]


def test_far_outside_is_rejected() -> None:
    outside = GeofenceMatch(FENCE, covers=False, distance_m=50)
    assert check(accuracy_m=10, match=outside) == (
        Verdict.REJECTED,
        GeofenceResult.OUTSIDE,
        [Reason.OUTSIDE_GEOFENCE],
    )


def test_outside_but_within_accuracy_is_flagged_for_review() -> None:
    near = GeofenceMatch(FENCE, covers=False, distance_m=20)
    assert check(accuracy_m=25, match=near) == (
        Verdict.FLAGGED_FOR_REVIEW,
        GeofenceResult.OUTSIDE,
        [Reason.BOUNDARY_UNCERTAIN],
    )


def test_mock_location_is_flagged_not_silently_accepted() -> None:
    assert check(is_mock=True) == (
        Verdict.FLAGGED_FOR_REVIEW,
        GeofenceResult.INSIDE,
        [Reason.MOCK_LOCATION_REPORTED],
    )


@pytest.mark.parametrize("is_mock", [False, None])
def test_unknown_mock_status_is_not_penalised(is_mock: bool | None) -> None:
    assert check(is_mock=is_mock)[0] is Verdict.VALIDATED


def test_campus_without_active_geofence_is_rejected() -> None:
    assert check(match=None) == (
        Verdict.REJECTED,
        GeofenceResult.NOT_EVALUATED,
        [Reason.NO_ACTIVE_GEOFENCE],
    )


def test_hard_reason_wins_over_soft_reasons_and_all_are_reported() -> None:
    near = GeofenceMatch(FENCE, covers=False, distance_m=5)
    verdict, _, reasons = check(age_s=60, is_mock=True, match=near)
    assert verdict is Verdict.REJECTED
    assert reasons == [
        Reason.LOCATION_TOO_OLD,
        Reason.MOCK_LOCATION_REPORTED,
        Reason.BOUNDARY_UNCERTAIN,
    ]
