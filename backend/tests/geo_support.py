"""Coordinates for tests: a fictional school around Parque Caldas, Popayán, and a
second campus in Cali (about 120 km away) for movement-plausibility tests."""

import math

POPAYAN = (2.4419, -76.6063)
CALI = (3.4516, -76.5320)


def offset(origin: tuple[float, float], north_m: float, east_m: float) -> tuple[float, float]:
    lat0, lng0 = origin
    m_per_deg_lng = 111_320.0 * math.cos(math.radians(lat0))
    return lat0 + north_m / 110_574.0, lng0 + east_m / m_per_deg_lng


def wkt_square(origin: tuple[float, float], half_side_m: float) -> str:
    corners = [(-1, -1), (-1, 1), (1, 1), (1, -1), (-1, -1)]
    points = []
    for n, e in corners:
        lat, lng = offset(origin, n * half_side_m, e * half_side_m)
        points.append(f"{lng} {lat}")
    return f"SRID=4326;POLYGON(({', '.join(points)}))"
