# ADR-003: PostGIS geospatial validation

- Status: Accepted
- Date: 2026-11-13

## Context

An attendance event is accepted only if the reported location is inside an
authorized campus area. Phone GPS readings come with an accuracy estimate
(typically 5–15 m outdoors, 20–60 m indoors). The project brief sets initial
values of a 100 m radius, 30 m maximum accuracy and 30 s maximum location age.
Campuses in Colombia are often irregular city blocks, not circles. The
decision must be made by the server, never by the app.

## Options considered

### Where to compute

1. **In Python** (Shapely + pyproj): the backend does the geometry itself.
   It needs a projection choice per campus, duplicates what the database can
   do, and cannot use a spatial index.
2. **In PostGIS**: geofences live in the database, and `ST_Covers` and
   `ST_Distance` run next to the data with a GiST index.

### How to store areas

1. **Centre + radius only.** Simple, but a circle covers the neighbours'
   houses on a rectangular block, and a long, narrow campus doesn't fit a
   circle at all.
2. **Polygons only.** Accurate, but a polygon is harder to configure for
   small schools.
3. **Polygons in storage, with two ways to create them.** Admins send a
   GeoJSON polygon, or a centre and radius that the server turns into a
   64-sided polygon (`ST_Buffer(..., 'quad_segs=16')`).

### Type

`GEOMETRY(POLYGON, 4326)` measures in degrees. Distances in metres would need
`ST_Transform` to a local projection. `GEOGRAPHY(POLYGON, 4326)` measures in
metres on the WGS84 ellipsoid, which is the unit every rule is expressed in.

## Decision

- **PostGIS, `GEOGRAPHY(POLYGON, 4326)`, GiST index, polygons in storage**
  (store option 3).
- **Validation of shapes:** pydantic checks the GeoJSON structure (one closed
  ring, 4–1000 positions, coordinates in range). PostGIS checks validity
  (`ST_IsValid`, with the reason returned to the admin). The area must be
  between 100 m² and 5 km² (configurable). The database also enforces
  `CHECK (ST_IsValid(area::geometry) AND ST_Area(area) > 0)` as a last line
  of defence.
- **The spatial question is asked once per check:** the nearest active
  geofence of the campus, whether it covers the point (`ST_Covers`, so a
  point on the boundary counts as inside, unlike `ST_Contains`), and the
  distance in metres (0 when inside).
- **The decision is a pure Python function**
  (`app/modules/geolocation/rules.py`) over that answer and the GPS
  metadata. It is unit-tested exhaustively without a database:

| Condition | Result |
|---|---|
| accuracy > 30 m | REJECTED `GPS_ACCURACY_TOO_LOW` |
| fix older than 30 s | REJECTED `LOCATION_TOO_OLD` |
| fix more than 5 s in the future (clock skew) | REJECTED `LOCATION_IN_FUTURE` |
| campus has no active geofence | REJECTED `NO_ACTIVE_GEOFENCE` |
| outside, and distance > accuracy | REJECTED `OUTSIDE_GEOFENCE` |
| outside, but distance ≤ accuracy | FLAGGED `BOUNDARY_UNCERTAIN` |
| OS reports a mock location | FLAGGED `MOCK_LOCATION_REPORTED` |
| none of the above | VALIDATED |

All reasons are reported, not just the first one, so the review screen can
show why. A rejection reason outranks a flag reason.

**Why flag rather than reject at the boundary:** the accuracy value is the
radius within which the true position probably lies. If that circle reaches
the geofence, the person may well be inside. Rejecting them would penalize
classrooms near the edge of the campus, and accepting them silently would
reward spoofers who stand just outside. A person reviews the case.

## Consequences

- Thresholds are settings today. Per-institution overrides come with the
  configurable attendance rules (advanced features).
- `POST /geofences/check` evaluates a reading **without storing it**. The
  admin dashboard uses it to test a geofence, and the attendance engine
  (Week 4) calls the same service.
- Only the nearest geofence is evaluated. Overlapping geofences are allowed
  and harmless: if any of them covers the point, its distance is 0, so it is
  the nearest.
- Geography operations are slower than geometry, but with the GiST index and
  few polygons per campus each check is a single index-assisted query.
  The Week 7 load test will measure it.
- Not covered yet: suspicious movement between consecutive events (FR-GEO-5).
  It needs event history and arrives with the attendance engine.

## How it is verified

- `tests/test_geo_rules.py`: every row of the table above, the thresholds at
  their exact limits, and combined reasons.
- `tests/test_geofences_api.py`, against real PostGIS with coordinates around
  Parque Caldas, Popayán:
  - the area of a 200 m square and of a 100 m circle (within 1 %);
  - a self-intersecting (bow-tie) polygon and implausible areas are rejected;
  - inside, near the edge, 50 m outside (distance checked to ±2 m), outside
    within the accuracy, stale and inaccurate fixes, mock locations;
  - the nearest of several geofences is the one used;
  - a geofence cannot be attached to another tenant's campus;
  - the GiST index is present.
