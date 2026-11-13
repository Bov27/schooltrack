# Campus maps

The dashboard draws each campus on a map (Leaflet) with its geofences, the latest
attendance events, a point tester and tools to draw a new geofence (polygon or circle).

## Tiles

| Layer | Source | Key | Notes |
|---|---|---|---|
| Mapa | OpenStreetMap (`tile.openstreetmap.org`) | none | Community servers: fine for a demo or a pilot, with the attribution shown. Heavy use is not allowed by the [tile usage policy](https://operations.osmfoundation.org/policies/tiles/). |
| Satélite | Esri World Imagery (`server.arcgisonline.com`) | none | Good for seeing buildings and courts. Check Esri's terms before commercial use. |

Both are defined in `apps/web/src/components/CampusMap.tsx` (`BASE_LAYERS`). For more
traffic, switch the URLs to a provider with a plan (for example MapTiler, Stadia Maps,
or Google's Map Tiles API) and keep the attribution they require. Nothing else changes:
the geofences come from the API as GeoJSON.

## Privacy

The tile servers receive the area being viewed (the campus), not people's locations:
event points are drawn by the browser from the API's data, and only School Admins see
them.
