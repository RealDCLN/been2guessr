"""Minimal client for Google's internal Street View panorama endpoints.

This module intentionally vendors only the small, metadata-only subset needed by
been2guessr. The request layouts were derived from the MIT-licensed
`streetlevel <https://github.com/sk-zk/streetlevel>`_ project; see
``NOTICE`` for attribution.

No Google API key is required. The endpoints are the same ones the Google Maps
web client uses and can change without notice.
"""

from __future__ import annotations

import asyncio
import json
import random
from typing import Any
from urllib.parse import quote

import httpx

from .models import Pano

COVERAGE_TILE_URL = (
    "https://www.google.com/maps/photometa/ac/v1"
    "?pb=!1m1!1smaps_sv.tactile!6m3!1i{tx}!2i{ty}!3i17!8b1"
)
FIND_URL = (
    "https://maps.googleapis.com/$rpc/google.internal.maps.mapsjs.v1.MapsJsInternalService/SingleImageSearch"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
THUMBNAIL_URL = (
    "https://streetviewpixels-pa.googleapis.com/v1/thumbnail"
    "?panoid={panoid}&cb_client=maps_sv.tactile&w=640&h=320&fov=90&pitch=0&yaw={heading}"
)


class PanoError(RuntimeError):
    """Raised when Google's panorama endpoints cannot be read."""


def is_third_party_panoid(panoid: str) -> bool:
    """Whether a pano ID belongs to a user photosphere rather than Google."""
    return panoid.startswith("CIHM0og") or len(panoid) > 22


def thumbnail_url(panoid: str, heading: int = 0) -> str:
    """Public thumbnail URL for a panorama (used by the web UI / previews)."""
    return THUMBNAIL_URL.format(panoid=quote(panoid), heading=int(heading) % 360)


# ---------------------------------------------------------------------------
# URL-encoded protobuf helper (only needed for the metadata-by-ID endpoint)
# ---------------------------------------------------------------------------


class _Enum:
    def __init__(self, value: int) -> None:
        self.value = value


def _datatype(value: Any) -> str:
    if isinstance(value, str):
        return "s"
    if isinstance(value, bool):
        return "b"
    if isinstance(value, _Enum):
        return "e"
    if isinstance(value, int):
        return "i"
    if isinstance(value, float):
        return "d"
    if isinstance(value, dict):
        return "m"
    raise TypeError(f"Unsupported protobuf value: {value!r}")


def _field(tag: int, value: Any) -> tuple[int, str]:
    if isinstance(value, list):
        count = 0
        text = ""
        for entry in value:
            sub_count, sub_text = _field(tag, entry)
            count += sub_count
            text += sub_text
        return count, text

    kind = _datatype(value)
    if kind == "m":
        sub_count, sub_text = _message(tag, value)
        return sub_count, sub_text
    if kind == "b":
        value = 1 if value else 0
    elif kind == "e":
        value = value.value
    return 1, f"!{tag}{kind}{value}"


def _message(tag: int, value: dict[int, Any]) -> tuple[int, str]:
    count = 0
    text = ""
    for key, entry in value.items():
        sub_count, sub_text = _field(key, entry)
        count += sub_count
        text += sub_text
    return count + 1, f"!{tag}m{count}{text}"


def to_protobuf_url(fields: dict[int, Any]) -> str:
    count = 0
    text = ""
    for key, value in fields.items():
        sub_count, sub_text = _field(key, value)
        count += sub_count
        text += sub_text
    return text


def _metadata_url(panoid: str, locale: str = "en") -> str:
    lang, _, country = locale.partition("-")
    country = country or lang
    pano_type = 10 if is_third_party_panoid(panoid) else 2
    toggles = [_Enum(x) for x in (1, 2, 3, 4, 5, 6, 8, 12)]
    message = {
        1: {1: "maps_sv.tactile", 11: {2: {1: True}}},
        2: {1: lang, 2: country},
        3: {1: {1: _Enum(pano_type), 2: panoid}},
        4: {
            1: toggles,
            2: {1: _Enum(1)},
            4: {1: 48},
            5: [{}],
            6: [{}],
            9: {
                1: [
                    {1: _Enum(2), 2: True, 3: _Enum(2)},
                    {1: _Enum(2), 2: False, 3: _Enum(3)},
                    {1: _Enum(3), 2: True, 3: _Enum(2)},
                    {1: _Enum(3), 2: False, 3: _Enum(3)},
                    {1: _Enum(8), 2: False, 3: _Enum(3)},
                    {1: _Enum(1), 2: False, 3: _Enum(3)},
                    {1: _Enum(4), 2: False, 3: _Enum(3)},
                    {1: _Enum(10), 2: True, 3: _Enum(2)},
                    {1: _Enum(10), 2: False, 3: _Enum(3)},
                ]
            },
            11: {3: {4: True}},
        },
    }
    return f"https://www.google.com/maps/photometa/v1?authuser=0&hl={lang}&gl={country}&pb=" + to_protobuf_url(
        message
    )


def _find_body(lat: float, lon: float, radius: float, third_party: bool, locale: str = "en") -> str:
    lang, _, country = locale.partition("-")
    country = country or lang
    image_type = 10 if third_party else 2
    message = [
        ["apiv3", None, None, None, "US"],
        [[None, None, lat, lon], float(radius)],
        [
            None,
            [lang, country],
            None,
            None,
            None,
            None,
            None,
            None,
            [2],
            None,
            [[[image_type, True, 2]]],
        ],
        [[1, 2, 3, 4, 6, 8, 12], None, None, None, [], []],
    ]
    return json.dumps(message)


# ---------------------------------------------------------------------------
# Response parsing (defensive: Google's arrays shift around)
# ---------------------------------------------------------------------------


def _get(fn, default=None):
    try:
        return fn()
    except (IndexError, KeyError, TypeError, ValueError):
        return default


def _dig(obj, *path, default=None):
    current = obj
    for key in path:
        try:
            current = current[key]
        except (IndexError, KeyError, TypeError):
            return default
    return current


def _parse_message(msg: list) -> Pano | None:
    panoid = _get(lambda: msg[1][1])
    if not panoid:
        return None

    lat = _get(lambda: msg[5][0][1][0][2])
    lon = _get(lambda: msg[5][0][1][0][3])
    if lat is None or lon is None:
        return None

    source = _get(lambda: str(msg[6][5][2]).lower())
    country = _get(lambda: msg[5][0][1][4])
    address = _get(lambda: [str(x[0]) for x in msg[3][2] if x and x[0]], [])

    date: str | None = None
    raw_date = _get(lambda: msg[6][7])
    if raw_date and len(raw_date) >= 2:
        if len(raw_date) >= 3 and raw_date[2]:
            date = f"{int(raw_date[0]):04d}-{int(raw_date[1]):02d}-{int(raw_date[2]):02d}"
        else:
            date = f"{int(raw_date[0]):04d}-{int(raw_date[1]):02d}"

    return Pano(
        id=str(panoid),
        lat=float(lat),
        lon=float(lon),
        source=source,
        country_code=str(country).upper() if country else None,
        date=date,
        address=address or [],
        third_party=is_third_party_panoid(str(panoid)),
    )


def parse_coverage_tile(payload: list) -> list[Pano]:
    """Parse the array returned by a zoom-17 coverage tile."""
    panos: list[Pano] = []
    raw_panos = _get(lambda: payload[1][1], []) or []

    for raw in raw_panos:
        # Some entries are metadata rather than a pano.
        if _dig(raw, 0, 0) == 1:
            continue
        panoid = _dig(raw, 0, 0, 1)
        lat = _dig(raw, 0, 2, 0, 2)
        lon = _dig(raw, 0, 2, 0, 3)
        if not panoid or lat is None or lon is None:
            continue
        panos.append(
            Pano(
                id=str(panoid),
                lat=float(lat),
                lon=float(lon),
                third_party=is_third_party_panoid(str(panoid)),
            )
        )
    return panos


def parse_find_response(payload: list) -> Pano | None:
    code = _get(lambda: payload[0][0])
    if code != 0:
        return None
    return _parse_message(_get(lambda: payload[1], []))


def parse_metadata_response(payload: list) -> Pano | None:
    code = _get(lambda: payload[1][0][0][0])
    if code not in (1, 3):
        return None
    return _parse_message(_get(lambda: payload[1][0], []))


def _decode(text: str) -> Any:
    text = text.strip()
    if text.startswith(")]}'"):
        text = text[4:].lstrip()
    return json.loads(text)


# ---------------------------------------------------------------------------
# Async client
# ---------------------------------------------------------------------------


class PanoClient:
    """Concurrent, retrying client for panorama discovery and metadata."""

    def __init__(self, *, concurrency: int = 12, timeout: float = 30.0) -> None:
        self._sem = asyncio.Semaphore(max(1, concurrency))
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
        )
        self._metadata_cache: dict[str, Pano | None] = {}

    async def __aenter__(self) -> PanoClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                async with self._sem:
                    response = await self._client.request(method, url, **kwargs)
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if response.status_code == 200:
                    return response
                if response.status_code == 403:
                    raise PanoError("Google refused the panorama request (403). Try again later.")
                if response.status_code != 429 and response.status_code < 500:
                    raise PanoError(f"Google returned HTTP {response.status_code}.")
                last_error = PanoError(f"Google returned HTTP {response.status_code}.")

            await asyncio.sleep(0.6 * (2**attempt) + random.random() * 0.4)

        raise PanoError(f"Panorama request failed after retries: {last_error}")

    async def coverage_tile(self, tile_x: int, tile_y: int) -> list[Pano]:
        """Most-recent official coverage in a zoom-17 tile."""
        url = COVERAGE_TILE_URL.format(tx=tile_x, ty=tile_y)
        response = await self._request("GET", url)
        return parse_coverage_tile(_decode(response.text))

    async def find_panorama(
        self,
        lat: float,
        lon: float,
        *,
        radius: float = 50,
        third_party: bool = False,
    ) -> Pano | None:
        """Nearest panorama within ``radius`` metres, or ``None``."""
        response = await self._request(
            "POST",
            FIND_URL,
            content=_find_body(lat, lon, radius, third_party),
            headers={"content-type": "application/json+protobuf"},
        )
        return parse_find_response(_decode(response.text))

    async def metadata(self, panoid: str) -> Pano | None:
        """Full metadata for a pano ID, or ``None`` if it no longer exists."""
        if panoid in self._metadata_cache:
            return self._metadata_cache[panoid]
        response = await self._request("GET", _metadata_url(panoid))
        result = parse_metadata_response(_decode(response.text))
        self._metadata_cache[panoid] = result
        return result
