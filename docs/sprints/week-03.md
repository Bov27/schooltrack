# Week 3: Geolocation

## Delivered

- [x] Migration `0003`: `geofences` as `GEOGRAPHY(POLYGON, 4326)` with a
      GiST index, a validity `CHECK`, unique names per campus, a composite
      foreign key to the campus, and forced RLS
- [x] Geofence creation from a GeoJSON polygon or from a centre + radius
      (a 64-sided polygon), with structure, validity and area checks
- [x] Spatial validation service: nearest active geofence, `ST_Covers`, and
      distance in metres
- [x] Decision rules as a pure function: accuracy, location age, clock skew,
      geofence, accuracy-aware boundary handling, mock locations
- [x] Endpoints: `POST /geofences` (School Admin), `GET /geofences`
      (members, optional `campus_id` filter), `POST /geofences/check`
      (a dry run that stores nothing)
- [x] ADR-003
- [x] Tests: decision rules (unit) and geofence API against PostGIS with
      Popayán coordinates

## Notes

- **The generic RLS-coverage test from Week 2 picked up the new table on its
  own:** `geofences` has `institution_id`, so CI would have failed if its
  policy had been forgotten.
- **Location privacy:** the check endpoint stores nothing. Coordinates are
  persisted only as part of an attendance event (Week 4), and the retention
  rules in the privacy notes apply.
- **Deferred:** suspicious-movement detection (it needs consecutive events,
  so it comes in Week 4 with the event log) and per-institution thresholds
  (configurable attendance rules).
