"""GeoGuessr map serialisation."""

from __future__ import annotations

import csv
import io
import random
import re

from .models import Pano
from .selector import BuildResult


def slugify(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return value or "map"


def _permalink(pano: Pano) -> str:
    pano_type = 10 if pano.third_party else 2
    return (
        f"https://www.google.com/maps/@{pano.lat:.7f},{pano.lon:.7f},3a,75y,0h,0t"
        f"/data=!3m4!1e1!3m2!1s{pano.id}!2e{pano_type}"
    )


def to_geoguessr(
    result: BuildResult,
    *,
    name: str | None = None,
    seed: int | None = None,
) -> dict:
    """Return the JSON object understood by the GeoGuessr map editor."""
    rng = random.Random(seed) if seed is not None else random.Random()
    coordinates = []
    for pano in result.panos:
        coordinates.append(
            {
                "heading": rng.randint(0, 359),
                "pitch": 0,
                "zoom": 0,
                "panoId": pano.id,
                "countryCode": pano.country_code,
                "stateCode": None,
                "lat": round(pano.lat, 7),
                "lng": round(pano.lon, 7),
            }
        )

    map_name = name or f"{result.username or 'BeenEverywhere'} - Places I've Been ({len(coordinates)})"
    return {"name": map_name, "customCoordinates": coordinates}


def to_array(result: BuildResult) -> list[dict]:
    """Just the location list, for importers that want a bare array."""
    return to_geoguessr(result)["customCoordinates"]


def to_csv(result: BuildResult) -> str:
    """Human-readable report for reviewing the picks."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "#",
            "place",
            "country",
            "panoId",
            "lat",
            "lng",
            "distance_m",
            "coverage",
            "capture_date",
            "google_maps_url",
        ]
    )
    for index, pano in enumerate(result.panos, 1):
        writer.writerow(
            [
                index,
                pano.place_label or "",
                pano.country_code or "",
                pano.id,
                f"{pano.lat:.7f}",
                f"{pano.lon:.7f}",
                round(pano.distance_m),
                "photosphere" if pano.third_party else (pano.source or "official"),
                pano.date or "",
                _permalink(pano),
            ]
        )
    return buffer.getvalue()


def filename(username: str | None, count: int, suffix: str = "json") -> str:
    return f"{slugify(username or 'been2guessr')}-geoguessr-{count}.{suffix}"
