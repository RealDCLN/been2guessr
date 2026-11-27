"""Client for BeenEverywhere public maps.

A public map lives at ``https://beeneverywhere.net/user/<username>`` and its
points are served as GeoJSON from ``/query-visits/<username>``. No login or
API key is involved.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from .geo import haversine_m
from .models import Place

BASE_URL = "https://beeneverywhere.net"
USER_AGENT = "been2guessr/0.1 (+https://github.com/RealDCLN/been2guessr)"

_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_URL_RE = re.compile(r"(?:https?://)?(?:www\.)?beeneverywhere\.net/user/([^/?#\s]+)", re.I)


class BeenEverywhereError(RuntimeError):
    """Raised when a BeenEverywhere map cannot be loaded."""


def parse_source(source: str) -> tuple[str, str | None]:
    """Extract ``(username, secret)`` from a username or profile URL.

    Accepts::

        your-username
        @your-username
        https://beeneverywhere.net/user/your-username
        https://beeneverywhere.net/user/your-username?secret=abc123
    """
    source = source.strip()
    if not source:
        raise BeenEverywhereError("Enter a BeenEverywhere username or profile URL.")

    secret: str | None = None
    username = source

    match = _URL_RE.search(source)
    if match:
        username = match.group(1)
        if "?" in source:
            from urllib.parse import parse_qs, urlparse

            query = parse_qs(urlparse(source).query)
            secret = (query.get("secret") or [None])[0]
    elif source.startswith("@"):
        username = source[1:]
    elif "://" in source or "/" in source:
        raise BeenEverywhereError(
            "That does not look like a BeenEverywhere profile. Use the username or "
            "https://beeneverywhere.net/user/<username>."
        )

    username = username.strip().strip("/")
    if not _USERNAME_RE.match(username):
        raise BeenEverywhereError(
            "Invalid username. Usernames may contain letters, numbers, dots, dashes and underscores."
        )
    return username, secret


def _places_from_geojson(payload: dict[str, Any], *, dedupe_m: float = 2.0) -> list[Place]:
    if payload.get("type") != "FeatureCollection":
        raise BeenEverywhereError("Unexpected response from BeenEverywhere (not GeoJSON).")

    places: list[Place] = []
    for feature in payload.get("features") or []:
        geometry = feature.get("geometry") or {}
        coords = geometry.get("coordinates")
        if not coords or len(coords) < 2:
            continue
        lon, lat = float(coords[0]), float(coords[1])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        props = feature.get("properties") or {}
        name = props.get("name") or props.get("title")
        cc = props.get("country_code") or props.get("countryCode")
        if cc:
            cc = str(cc).upper()

        # BeenEverywhere sometimes has near-duplicate points; avoid paying for
        # the same tile twice.
        if any(haversine_m(lat, lon, p.lat, p.lon) <= dedupe_m for p in places):
            continue

        places.append(Place(index=len(places), lat=lat, lon=lon, name=name, country_code=cc))

    if not places:
        raise BeenEverywhereError("This map has no visited places.")
    return places


def fetch_map(
    source: str,
    *,
    timeout: float = 30.0,
) -> tuple[str, list[Place], dict[str, Any]]:
    """Fetch a public BeenEverywhere map.

    Returns ``(username, places, raw_payload)``. The raw payload includes the
    site's own statistics, which are handy for summaries.
    """
    username, secret = parse_source(source)
    url = f"{BASE_URL}/query-visits/{username}"
    params = {"secret": secret} if secret else None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise BeenEverywhereError(f"Could not reach BeenEverywhere: {exc}") from exc

    if response.status_code == 404:
        raise BeenEverywhereError(
            f'No map found for "{username}". Check the username or make the map public.'
        )
    if response.status_code != 200:
        raise BeenEverywhereError(f"BeenEverywhere returned HTTP {response.status_code}.")

    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise BeenEverywhereError("BeenEverywhere returned invalid JSON.") from exc

    if isinstance(payload, dict) and payload.get("error"):
        raise BeenEverywhereError(f"BeenEverywhere says: {payload['error']}")

    return username, _places_from_geojson(payload), payload


def load_map_file(path: str | Path) -> list[Place]:
    """Load a saved ``query-visits`` JSON file."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BeenEverywhereError(f"Could not read {path}: {exc}") from exc
    return _places_from_geojson(payload)


def load_map_json(text: str) -> list[Place]:
    """Load a GeoJSON document that was pasted into the web UI."""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BeenEverywhereError(f"Invalid JSON: {exc}") from exc
    return _places_from_geojson(payload)
