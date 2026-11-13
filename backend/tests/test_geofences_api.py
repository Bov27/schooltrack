"""Geofences and location checks against real PostGIS.

Fictional school around Parque Caldas, Popayán (2.4419 N, 76.6063 W). Offsets are in
metres; at this latitude 1° of latitude ≈ 110 574 m and 1° of longitude ≈ 111 219 m.
"""

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.db_support import Factory, auth, requires_database

pytestmark = [requires_database]

CENTER_LAT, CENTER_LNG = 2.4419, -76.6063
M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LNG = 111_320.0 * math.cos(math.radians(CENTER_LAT))
HALF_SIDE_M = 100  # geofence: 200 m x 200 m square around the centre


def offset(north_m: float, east_m: float) -> tuple[float, float]:
    """(lat, lng) of the point north_m / east_m metres from the centre."""
    return CENTER_LAT + north_m / M_PER_DEG_LAT, CENTER_LNG + east_m / M_PER_DEG_LNG


def square(half_side_m: float) -> dict[str, Any]:
    corners = [(-1, -1), (-1, 1), (1, 1), (1, -1), (-1, -1)]
    ring = []
    for n, e in corners:
        lat, lng = offset(n * half_side_m, e * half_side_m)
        ring.append([lng, lat])  # GeoJSON order
    return {"type": "Polygon", "coordinates": [ring]}


@dataclass
class School:
    a: uuid.UUID
    b: uuid.UUID
    campus_a: uuid.UUID
    campus_b: uuid.UUID


@pytest.fixture
def school(factory: Factory) -> School:
    a, b = factory.institution("colegio-a"), factory.institution("colegio-b")
    factory.member(a, factory.user("admin@colegio-a.test"), "SCHOOL_ADMIN")
    factory.member(a, factory.user("student@colegio-a.test"), "STUDENT")
    factory.member(b, factory.user("admin@colegio-b.test"), "SCHOOL_ADMIN")
    return School(a, b, factory.campus(a, "Sede Centro"), factory.campus(b, "Sede B"))


def create(api: TestClient, school: School, **body: Any) -> Any:
    payload = {"campus_id": str(school.campus_a), "name": "Perímetro", **body}
    return api.post("/api/v1/geofences", json=payload, headers=auth(api, "admin@colegio-a.test"))


def check(
    api: TestClient,
    school: School,
    north_m: float = 0,
    east_m: float = 0,
    *,
    accuracy_m: float = 10,
    age_s: float = 2,
    is_mock: bool | None = None,
    email: str = "student@colegio-a.test",
) -> dict[str, Any]:
    lat, lng = offset(north_m, east_m)
    body: dict[str, Any] = {
        "campus_id": str(school.campus_a),
        "latitude": lat,
        "longitude": lng,
        "accuracy_m": accuracy_m,
        "captured_at": (datetime.now(UTC) - timedelta(seconds=age_s)).isoformat(),
    }
    if is_mock is not None:
        body["is_mock"] = is_mock
    response = api.post("/api/v1/geofences/check", json=body, headers=auth(api, email))
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


# ---- creating geofences -----------------------------------------------------------

def test_create_polygon_geofence(api: TestClient, school: School) -> None:
    response = create(api, school, area=square(HALF_SIDE_M))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["area"]["type"] == "Polygon"
    assert body["area_m2"] == pytest.approx(200 * 200, rel=0.01)


def test_create_from_centre_and_radius(api: TestClient, school: School) -> None:
    response = create(
        api, school, center={"latitude": CENTER_LAT, "longitude": CENTER_LNG}, radius_m=100
    )
    assert response.status_code == 201, response.text
    assert response.json()["area_m2"] == pytest.approx(math.pi * 100**2, rel=0.01)


def test_default_radius_is_100_m(api: TestClient, school: School) -> None:
    response = create(api, school, center={"latitude": CENTER_LAT, "longitude": CENTER_LNG})
    assert response.json()["area_m2"] == pytest.approx(math.pi * 100**2, rel=0.01)


def test_self_intersecting_polygon_is_rejected(api: TestClient, school: School) -> None:
    (a, b), (c, d) = offset(-100, -100), offset(100, 100)
    bow_tie = {"type": "Polygon", "coordinates": [[[b, a], [d, c], [d, a], [b, c], [b, a]]]}
    response = create(api, school, area=bow_tie)
    assert response.status_code == 422
    assert "Invalid polygon" in response.json()["error"]["message"]


def test_unclosed_ring_is_rejected(api: TestClient, school: School) -> None:
    ring = square(HALF_SIDE_M)["coordinates"][0][:-1]
    response = create(api, school, area={"type": "Polygon", "coordinates": [ring]})
    assert response.status_code == 422


@pytest.mark.parametrize("half_side_m", [3, 2000])  # 36 m² and 16 km²
def test_implausible_area_is_rejected(api: TestClient, school: School, half_side_m: int) -> None:
    response = create(api, school, area=square(half_side_m))
    assert response.status_code == 422
    assert "allowed range" in response.json()["error"]["message"]


def test_polygon_and_centre_together_are_rejected(api: TestClient, school: School) -> None:
    response = create(
        api, school, area=square(HALF_SIDE_M), center={"latitude": 2.44, "longitude": -76.6}
    )
    assert response.status_code == 422


def test_duplicate_name_on_same_campus_conflicts(api: TestClient, school: School) -> None:
    assert create(api, school, area=square(HALF_SIDE_M)).status_code == 201
    assert create(api, school, area=square(HALF_SIDE_M)).status_code == 409


def test_student_cannot_create_geofences(api: TestClient, school: School) -> None:
    response = api.post(
        "/api/v1/geofences",
        json={"campus_id": str(school.campus_a), "name": "X", "area": square(HALF_SIDE_M)},
        headers=auth(api, "student@colegio-a.test"),
    )
    assert response.status_code == 403


def test_cannot_attach_a_geofence_to_another_schools_campus(
    api: TestClient, school: School
) -> None:
    response = create(api, school, campus_id=str(school.campus_b), area=square(HALF_SIDE_M))
    assert response.status_code == 404


def test_list_is_scoped_to_the_institution(api: TestClient, school: School) -> None:
    create(api, school, area=square(HALF_SIDE_M))
    mine = api.get("/api/v1/geofences", headers=auth(api, "student@colegio-a.test"))
    theirs = api.get("/api/v1/geofences", headers=auth(api, "admin@colegio-b.test"))
    assert [g["name"] for g in mine.json()] == ["Perímetro"]
    assert theirs.json() == []


def test_list_can_filter_by_campus(
    api: TestClient, school: School, factory: Factory
) -> None:
    other_campus = factory.campus(school.a, "Sede Norte")
    create(api, school, area=square(HALF_SIDE_M))
    response = api.get(
        "/api/v1/geofences",
        params={"campus_id": str(other_campus)},
        headers=auth(api, "admin@colegio-a.test"),
    )
    assert response.status_code == 200
    assert response.json() == []


# ---- checking locations (nothing stored) ----------------------------------------------

@pytest.fixture
def fenced(api: TestClient, school: School) -> School:
    assert create(api, school, area=square(HALF_SIDE_M)).status_code == 201
    return school


def test_centre_is_inside(api: TestClient, fenced: School) -> None:
    result = check(api, fenced)
    assert result["verdict"] == "VALIDATED"
    assert result["geofence_result"] == "INSIDE"
    assert result["distance_m"] == 0


def test_just_inside_the_edge_is_inside(api: TestClient, fenced: School) -> None:
    assert check(api, fenced, north_m=95)["geofence_result"] == "INSIDE"


def test_well_outside_is_rejected_with_distance(api: TestClient, fenced: School) -> None:
    result = check(api, fenced, north_m=HALF_SIDE_M + 50, accuracy_m=10)
    assert result["verdict"] == "REJECTED"
    assert result["reasons"] == ["OUTSIDE_GEOFENCE"]
    assert result["distance_m"] == pytest.approx(50, abs=2)


def test_outside_within_gps_accuracy_is_flagged(api: TestClient, fenced: School) -> None:
    result = check(api, fenced, east_m=HALF_SIDE_M + 15, accuracy_m=25)
    assert result["verdict"] == "FLAGGED_FOR_REVIEW"
    assert result["reasons"] == ["BOUNDARY_UNCERTAIN"]


def test_inaccurate_fix_is_rejected(api: TestClient, fenced: School) -> None:
    result = check(api, fenced, accuracy_m=45)
    assert result["verdict"] == "REJECTED"
    assert result["reasons"] == ["GPS_ACCURACY_TOO_LOW"]


def test_stale_fix_is_rejected(api: TestClient, fenced: School) -> None:
    assert check(api, fenced, age_s=120)["reasons"] == ["LOCATION_TOO_OLD"]


def test_mock_location_is_flagged(api: TestClient, fenced: School) -> None:
    result = check(api, fenced, is_mock=True)
    assert result["verdict"] == "FLAGGED_FOR_REVIEW"
    assert result["reasons"] == ["MOCK_LOCATION_REPORTED"]


def test_nearest_of_several_geofences_is_used(api: TestClient, fenced: School) -> None:
    lat, lng = offset(400, 0)
    response = create(
        api, fenced, name="Cancha", center={"latitude": lat, "longitude": lng}, radius_m=50
    )
    assert response.status_code == 201
    result = check(api, fenced, north_m=400)
    assert result["verdict"] == "VALIDATED"
    assert result["geofence_id"] == response.json()["id"]


def test_campus_without_geofence_is_rejected(api: TestClient, school: School) -> None:
    result = check(api, school)
    assert result["verdict"] == "REJECTED"
    assert result["reasons"] == ["NO_ACTIVE_GEOFENCE"]
    assert result["geofence_result"] == "NOT_EVALUATED"


def test_check_against_another_schools_campus_is_not_found(
    api: TestClient, fenced: School
) -> None:
    lat, lng = offset(0, 0)
    response = api.post(
        "/api/v1/geofences/check",
        json={
            "campus_id": str(fenced.campus_b),
            "latitude": lat,
            "longitude": lng,
            "accuracy_m": 5,
            "captured_at": datetime.now(UTC).isoformat(),
        },
        headers=auth(api, "student@colegio-a.test"),
    )
    assert response.status_code == 404


def test_naive_timestamp_is_rejected(api: TestClient, fenced: School) -> None:
    response = api.post(
        "/api/v1/geofences/check",
        json={
            "campus_id": str(fenced.campus_a),
            "latitude": CENTER_LAT,
            "longitude": CENTER_LNG,
            "accuracy_m": 5,
            "captured_at": "2027-02-01T07:00:00",
        },
        headers=auth(api, "student@colegio-a.test"),
    )
    assert response.status_code == 422


def test_gist_index_is_used_for_geofence_lookups(owner_conn: Any, fenced: School) -> None:
    indexes = owner_conn.execute(
        "SELECT indexdef FROM pg_indexes WHERE tablename = 'geofences'"
    ).fetchall()
    assert any("USING gist (area)" in row[0] for row in indexes)


# ---- managing geofences ---------------------------------------------------------------

def test_deactivated_geofence_is_ignored_by_validation(api: TestClient, fenced: School) -> None:
    admin = auth(api, "admin@colegio-a.test")
    [geofence] = api.get("/api/v1/geofences", headers=admin).json()
    off = api.patch(f"/api/v1/geofences/{geofence['id']}", json={"is_active": False}, headers=admin)
    assert off.status_code == 200
    assert off.json()["is_active"] is False
    assert check(api, fenced)["reasons"] == ["NO_ACTIVE_GEOFENCE"]

    on = api.patch(f"/api/v1/geofences/{geofence['id']}", json={"is_active": True}, headers=admin)
    assert on.json()["is_active"] is True
    assert check(api, fenced)["verdict"] == "VALIDATED"


def test_rename_and_audit(api: TestClient, fenced: School, owner_conn: Any) -> None:
    admin = auth(api, "admin@colegio-a.test")
    [geofence] = api.get("/api/v1/geofences", headers=admin).json()
    renamed = api.patch(
        f"/api/v1/geofences/{geofence['id']}", json={"name": "Patio"}, headers=admin
    )
    assert renamed.json()["name"] == "Patio"
    actions = owner_conn.execute(
        "SELECT action FROM audit_logs WHERE entity_id = %s", (geofence["id"],)
    ).fetchall()
    assert actions == [("geofence.updated",)]


def test_unused_geofence_can_be_deleted(api: TestClient, fenced: School) -> None:
    admin = auth(api, "admin@colegio-a.test")
    [geofence] = api.get("/api/v1/geofences", headers=admin).json()
    assert api.delete(f"/api/v1/geofences/{geofence['id']}", headers=admin).status_code == 204
    assert api.get("/api/v1/geofences", headers=admin).json() == []
    assert api.delete(f"/api/v1/geofences/{geofence['id']}", headers=admin).status_code == 404


def test_geofence_used_by_events_cannot_be_deleted(
    api: TestClient, fenced: School, factory: Factory
) -> None:
    student = factory.user("ana@colegio-a.test")
    factory.member(fenced.a, student, "STUDENT")
    factory.student(fenced.a, "A-001", student)
    now = datetime.now(UTC)
    lat, lng = offset(0, 0)
    recorded = api.post(
        "/api/v1/attendance/events",
        json={
            "idempotency_key": str(uuid.uuid4()),
            "event_type": "CHECK_IN",
            "campus_id": str(fenced.campus_a),
            "occurred_at": now.isoformat(),
            "latitude": lat,
            "longitude": lng,
            "accuracy_m": 5,
            "location_captured_at": now.isoformat(),
        },
        headers=auth(api, "ana@colegio-a.test"),
    )
    assert recorded.status_code == 201
    admin = auth(api, "admin@colegio-a.test")
    geofence_id = api.get("/api/v1/geofences", headers=admin).json()[0]["id"]
    response = api.delete(f"/api/v1/geofences/{geofence_id}", headers=admin)
    assert response.status_code == 409
    assert "deactivate it instead" in response.json()["error"]["message"]


def test_students_cannot_manage_geofences(api: TestClient, fenced: School) -> None:
    [geofence] = api.get("/api/v1/geofences", headers=auth(api, "admin@colegio-a.test")).json()
    student = auth(api, "student@colegio-a.test")
    url = f"/api/v1/geofences/{geofence['id']}"
    assert api.patch(url, json={"is_active": False}, headers=student).status_code == 403
    assert api.delete(url, headers=student).status_code == 403


def test_other_school_cannot_touch_the_geofence(api: TestClient, fenced: School) -> None:
    [geofence] = api.get("/api/v1/geofences", headers=auth(api, "admin@colegio-a.test")).json()
    other = auth(api, "admin@colegio-b.test")
    url = f"/api/v1/geofences/{geofence['id']}"
    assert api.patch(url, json={"is_active": False}, headers=other).status_code == 404
    assert api.delete(url, headers=other).status_code == 404
