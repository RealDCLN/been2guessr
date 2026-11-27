"""High-level build functions shared by the CLI and web app."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .beeneverywhere import fetch_map, load_map_file
from .models import BuildOptions, Place, Progress
from .selector import BuildResult, ProgressFn, build_map


async def build_from_source(
    source: str,
    options: BuildOptions,
    *,
    progress: ProgressFn | None = None,
) -> BuildResult:
    """Fetch a public BeenEverywhere map and build a GeoGuessr map from it."""
    username, places, payload = await asyncio.to_thread(fetch_map, source)
    result = await build_map(
        places,
        options,
        username=username,
        source_stats=payload.get("stats") or {},
        progress=progress,
    )
    result.source_stats.setdefault("places_visited", len(places))
    return result


async def build_from_places(
    places: list[Place],
    options: BuildOptions,
    *,
    username: str | None = None,
    progress: ProgressFn | None = None,
) -> BuildResult:
    return await build_map(places, options, username=username, progress=progress)


async def build_from_file(
    path: str | Path,
    options: BuildOptions,
    *,
    progress: ProgressFn | None = None,
) -> BuildResult:
    places = await asyncio.to_thread(load_map_file, path)
    return await build_map(places, options, username=Path(path).stem, progress=progress)


def summarize(result: BuildResult) -> dict[str, Any]:
    """JSON-friendly summary used by the web UI."""
    stats = result.stats
    return {
        "produced": stats.produced,
        "requested": stats.requested,
        "places_total": stats.places_total,
        "places_covered": stats.places_covered,
        "official": stats.official,
        "third_party": stats.third_party,
        "countries": stats.countries,
        "skipped_places": stats.skipped_places,
        "warnings": stats.warnings,
        "username": result.username,
        "places_visited": result.source_stats.get("places_visited"),
    }


def run_sync(coro):
    """Run a coroutine from a sync context (handy for scripts and notebooks)."""
    return asyncio.run(coro)


__all__ = [
    "BuildResult",
    "Progress",
    "build_from_file",
    "build_from_places",
    "build_from_source",
    "summarize",
]
