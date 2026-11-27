"""Small geography helpers used for panorama discovery and selection."""

from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points in metres."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial bearing from point 1 to point 2, in degrees (0 = north)."""
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def tile_xy(lat: float, lon: float, zoom: int = 17) -> tuple[int, int]:
    """Convert WGS84 coordinates to an XYZ tile coordinate."""
    scale = 1 << zoom
    lat_rad = math.radians(lat)
    x = (lon + 180.0) / 360.0 * scale
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * scale
    return int(x), int(y)


def ring_tiles(cx: int, cy: int, radius: int) -> list[tuple[int, int]]:
    """Return the tiles exactly ``radius`` rings away from ``(cx, cy)``."""
    if radius <= 0:
        return [(cx, cy)]
    tiles: list[tuple[int, int]] = []
    for dx in range(-radius, radius + 1):
        for dy in range(-radius, radius + 1):
            if max(abs(dx), abs(dy)) == radius:
                tiles.append((cx + dx, cy + dy))
    return tiles


def box_tiles(cx: int, cy: int, radius: int) -> list[tuple[int, int]]:
    """Return all tiles in a square of ``radius`` rings around ``(cx, cy)``."""
    return [(cx + dx, cy + dy) for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1)]
