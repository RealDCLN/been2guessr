"""Panorama discovery, quality filtering and location selection."""

from __future__ import annotations

import asyncio
import math
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from .geo import box_tiles, haversine_m, ring_tiles, tile_xy
from .models import BuildOptions, BuildStats, Pano, Place, Progress
from .panos import PanoClient, PanoError

ProgressFn = Callable[[Progress], None]


@dataclass(slots=True)
class BuildResult:
    panos: list[Pano]
    stats: BuildStats
    username: str | None = None
    source_stats: dict = field(default_factory=dict)


def _noop(_: Progress) -> None:
    pass


# ---------------------------------------------------------------------------
# Candidate discovery
# ---------------------------------------------------------------------------


class _TileCache:
    """Share coverage-tile requests between nearby places."""

    def __init__(self, client: PanoClient) -> None:
        self._client = client
        self._tasks: dict[tuple[int, int], asyncio.Task[list[Pano]]] = {}
        self.errors = 0
        self.requests = 0

    async def get(self, tx: int, ty: int) -> list[Pano]:
        key = (tx, ty)
        task = self._tasks.get(key)
        if task is None:
            task = asyncio.create_task(self._fetch(tx, ty))
            self._tasks[key] = task
        return await task

    async def _fetch(self, tx: int, ty: int) -> list[Pano]:
        self.requests += 1
        try:
            return await self._client.coverage_tile(tx, ty)
        except PanoError:
            self.errors += 1
            return []


async def _safe_find(
    client: PanoClient, lat: float, lon: float, radius: float, third_party: bool
) -> Pano | None:
    try:
        return await client.find_panorama(lat, lon, radius=radius, third_party=third_party)
    except PanoError:
        return None


async def _collect_place(
    client: PanoClient,
    tiles: _TileCache,
    place: Place,
    options: BuildOptions,
) -> list[Pano]:
    cx, cy = tile_xy(place.lat, place.lon)
    found: dict[str, Pano] = {}
    soft_limit = max(options.max_radius_m, 4_000.0)

    def add(pano: Pano, limit: float) -> None:
        if pano.id in found:
            return
        distance = haversine_m(place.lat, place.lon, pano.lat, pano.lon)
        if distance <= limit:
            pano.distance_m = distance
            found[pano.id] = pano

    async def add_tiles(coords: list[tuple[int, int]]) -> None:
        results = await asyncio.gather(*(tiles.get(tx, ty) for tx, ty in coords))
        for tile in results:
            for pano in tile:
                add(pano, options.max_radius_m)

    # Official coverage tiles. Most places are fully covered by the 3x3 block.
    await add_tiles(box_tiles(cx, cy, 1))
    if len(found) < 6:
        await add_tiles(ring_tiles(cx, cy, 2))

    # Remote villages and trekker coverage sometimes sit outside the tile data.
    if len(found) < 3:
        for radius in (400, 1_200, 4_000):
            pano = await _safe_find(client, place.lat, place.lon, radius, False)
            if pano:
                add(pano, soft_limit)
            if len(found) >= 3:
                break

    # Real user photospheres, only when official coverage is thin.
    if len(found) < 2 and options.include_photospheres and not options.official_only:
        for radius in (800, 2_500):
            pano = await _safe_find(client, place.lat, place.lon, radius, True)
            if pano:
                add(pano, soft_limit)

        third_party_count = sum(1 for p in found.values() if p.third_party)
        if third_party_count < 2:
            # Probe a small grid so we get more than one sphere on tiny islands.
            step_lat = 0.0036  # ~400 m
            step_lon = step_lat / max(0.2, math.cos(math.radians(place.lat)))
            probes = [
                (place.lat + dy * step_lat, place.lon + dx * step_lon)
                for dy in range(-3, 4)
                for dx in range(-3, 4)
                if dx or dy
            ]
            results = await asyncio.gather(*(_safe_find(client, lat, lon, 350, True) for lat, lon in probes))
            for pano in results:
                if pano:
                    add(pano, soft_limit)

    return list(found.values())


# ---------------------------------------------------------------------------
# Pool building, metadata and ranking
# ---------------------------------------------------------------------------


def _spread_pool(candidates: list[Pano], options: BuildOptions) -> list[Pano]:
    """Pick a spatially spread subset, nearest to the visited point first."""
    ordered = sorted(candidates, key=lambda p: p.distance_m)

    def spread(min_sep: float, want: int) -> list[Pano]:
        out: list[Pano] = []
        for pano in ordered:
            if all(haversine_m(pano.lat, pano.lon, other.lat, other.lon) >= min_sep for other in out):
                out.append(pano)
            if len(out) >= want:
                break
        return out

    separation = 260.0 if len(ordered) > 250 else 190.0
    pool = spread(separation, options.pool_size)
    if len(pool) < 5:
        pool = spread(90.0, options.pool_size)
    if len(pool) < 3:
        pool = spread(40.0, options.pool_size)
    return pool


def _label_from(pano: Pano | None, place: Place) -> str:
    if pano and pano.address:
        for line in reversed(pano.address):
            candidate = line.split(",")[0].strip()
            if candidate and not candidate.lower().startswith("decentralized administration"):
                return candidate
    return place.label


def _score(pano: Pano, options: BuildOptions) -> float:
    score = pano.distance_m
    if pano.source != "launch":
        score += 220.0
    if pano.third_party:
        score += 900.0
    if pano.source is None and not pano.third_party:
        score += 150.0
    if options.prefer_recent and pano.date:
        try:
            year = int(pano.date[:4])
            score += max(0, 2016 - year) * 25.0
        except ValueError:
            pass
    return score


async def _read_metadata(
    client: PanoClient,
    pools: dict[int, list[Pano]],
    options: BuildOptions,
    progress: ProgressFn,
) -> dict[str, Pano | None]:
    ids = sorted({pano.id for pool in pools.values() for pano in pool})
    results: dict[str, Pano | None] = {}
    done = 0
    total = len(ids)
    lock = asyncio.Lock()

    async def one(panoid: str) -> None:
        nonlocal done
        try:
            pano = await client.metadata(panoid)
        except PanoError:
            pano = None
        results[panoid] = pano
        async with lock:
            done += 1
            if done % 25 == 0 or done == total:
                progress(Progress("panoramas", done, total, "Reading panorama metadata"))

    await asyncio.gather(*(one(panoid) for panoid in ids))
    return results


def _merge_metadata(candidate: Pano, metadata: Pano | None) -> Pano:
    if metadata is None:
        merged = Pano(
            id=candidate.id,
            lat=candidate.lat,
            lon=candidate.lon,
            third_party=candidate.third_party,
        )
    else:
        merged = Pano(
            id=metadata.id,
            lat=metadata.lat,
            lon=metadata.lon,
            source=metadata.source,
            country_code=metadata.country_code,
            date=metadata.date,
            address=list(metadata.address),
            third_party=metadata.third_party,
        )
    merged.distance_m = candidate.distance_m
    merged.score = candidate.score
    return merged


def _rank_place(
    place: Place,
    candidates: list[Pano],
    metadata: dict[str, Pano | None],
    options: BuildOptions,
) -> list[Pano]:
    merged = [_merge_metadata(candidate, metadata.get(candidate.id)) for candidate in candidates]
    merged = [pano for pano in merged if pano.source not in ("innerspace", "cultural_institute")]

    official = [pano for pano in merged if not pano.third_party]
    if len(official) >= 2:
        merged = official
    elif options.official_only:
        merged = official

    if not merged:
        return []

    label_pano = min(merged, key=lambda p: p.distance_m)
    label = _label_from(label_pano, place)
    for pano in merged:
        pano.place_index = place.index
        pano.place_label = label
        pano.score = _score(pano, options)

    merged.sort(key=lambda p: (p.score, p.distance_m, p.id))
    return merged


# ---------------------------------------------------------------------------
# Allocation and global de-duplication
# ---------------------------------------------------------------------------


def allocate_targets(
    available: dict[int, int],
    count: int,
    per_place_min: int,
    per_place_max: int,
) -> dict[int, int]:
    """Decide how many panoramas each place should contribute.

    The function is pure so it can be unit tested without network access.
    """
    usable = {index: n for index, n in available.items() if n > 0}
    if not usable or count <= 0:
        return {}

    order = sorted(usable, key=lambda index: (-usable[index], index))

    if count <= len(usable):
        return {index: 1 for index in order[:count]}

    targets = dict.fromkeys(usable, 0)
    remaining = count

    for index in order:
        take = min(max(0, per_place_min), usable[index])
        targets[index] = take
        remaining -= take

    while remaining > 0:
        progressed = False
        for index in order:
            if remaining <= 0:
                break
            if targets[index] < min(per_place_max, usable[index]):
                targets[index] += 1
                remaining -= 1
                progressed = True
        if not progressed:
            break

    return targets


def select_global(
    ranked: dict[int, list[Pano]],
    targets: dict[int, int],
    desired: int,
    min_spacing_m: float,
    per_place_max: int,
) -> list[Pano]:
    """Pick panos per place, enforcing a global minimum spacing."""
    order = sorted(ranked, key=lambda index: (-len(ranked[index]), index))
    chosen: dict[int, list[Pano]] = {index: [] for index in ranked}
    pointers: dict[int, int] = dict.fromkeys(ranked, 0)
    used: list[Pano] = []
    used_ids: set[str] = set()

    def advance(index: int) -> bool:
        pool = ranked[index]
        while pointers[index] < len(pool):
            pano = pool[pointers[index]]
            pointers[index] += 1
            if pano.id in used_ids:
                continue
            if any(haversine_m(pano.lat, pano.lon, other.lat, other.lon) < min_spacing_m for other in used):
                continue
            chosen[index].append(pano)
            used.append(pano)
            used_ids.add(pano.id)
            return True
        return False

    rounds = max(targets.values(), default=0)
    for _ in range(rounds):
        for index in order:
            if len(chosen[index]) < targets.get(index, 0):
                advance(index)

    total = len(used)
    while total < desired:
        progressed = False
        for index in order:
            if total >= desired:
                break
            if len(chosen[index]) >= min(per_place_max, len(ranked[index])):
                continue
            if advance(index):
                total += 1
                progressed = True
        if not progressed:
            break

    return [pano for index in sorted(chosen) for pano in chosen[index]][:desired]


def _fill_missing_countries(panos: list[Pano]) -> None:
    known = [pano for pano in panos if pano.country_code]
    for pano in panos:
        if pano.country_code or not known:
            continue
        nearest = min(known, key=lambda other: haversine_m(pano.lat, pano.lon, other.lat, other.lon))
        if haversine_m(pano.lat, pano.lon, nearest.lat, nearest.lon) <= 50_000:
            pano.country_code = nearest.country_code


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def build_map(
    places: list[Place],
    options: BuildOptions,
    *,
    username: str | None = None,
    source_stats: dict | None = None,
    progress: ProgressFn | None = None,
) -> BuildResult:
    """Find panoramas for every place and pick a balanced subset."""
    options.validate()
    progress = progress or _noop
    warnings: list[str] = []

    async with PanoClient(concurrency=options.concurrency) as client:
        tiles = _TileCache(client)

        progress(Progress("places", 0, len(places), "Looking for panoramas near each place"))

        async def collect(place: Place) -> tuple[Place, list[Pano]]:
            return place, await _collect_place(client, tiles, place, options)

        tasks = [asyncio.create_task(collect(place)) for place in places]
        candidates: dict[int, list[Pano]] = {}
        done = 0
        for finished in asyncio.as_completed(tasks):
            place, pool = await finished
            candidates[place.index] = pool
            done += 1
            progress(Progress("places", done, len(places), "Looking for panoramas near each place"))

        if tiles.errors and tiles.requests and tiles.errors > tiles.requests * 0.6:
            raise PanoError(
                "Most panorama requests failed. Google may be rate-limiting this network; "
                "wait a few minutes and try again."
            )

        empty = [place for place in places if not candidates.get(place.index)]
        if len(empty) == len(places):
            raise PanoError("No panoramas could be found for this map.")

        pools = {
            place.index: _spread_pool(candidates[place.index], options)
            for place in places
            if candidates.get(place.index)
        }

        progress(Progress("panoramas", 0, 1, "Reading panorama metadata"))
        metadata = await _read_metadata(client, pools, options, progress)

    ranked: dict[int, list[Pano]] = {}
    for place in places:
        pool = pools.get(place.index)
        if not pool:
            continue
        ordered = _rank_place(place, pool, metadata, options)
        if ordered:
            ranked[place.index] = ordered

    available = {index: len(pool) for index, pool in ranked.items()}
    targets = allocate_targets(
        available,
        options.count,
        options.per_place_min,
        options.per_place_max,
    )

    progress(Progress("selecting", 0, 1, "Selecting a varied set of locations"))
    selected: list[Pano] = []
    for spacing in (options.min_spacing_m, max(40.0, options.min_spacing_m * 0.4), 1.0):
        selected = select_global(ranked, targets, options.count, spacing, options.per_place_max)
        if len(selected) >= options.count:
            break
        if spacing == 1.0:
            break
    selected = selected[: options.count]

    _fill_missing_countries(selected)

    covered = {pano.place_index for pano in selected if pano.place_index is not None}
    uncovered = [place for place in places if place.index not in ranked]
    skipped = [place.label for place in uncovered]
    if skipped:
        warnings.append(f"{len(skipped)} place(s) had no usable Street View coverage and were skipped.")
    if options.count < len(ranked):
        warnings.append(
            f"You asked for {options.count} locations, so {len(covered)} of {len(places)} "
            "places are represented. Increase the count to cover more places."
        )
    if len(selected) < options.count:
        warnings.append(
            f"Only {len(selected)} of the requested {options.count} locations could be built. "
            "Try a larger search radius or enable photospheres."
        )

    countries = Counter(pano.country_code or "??" for pano in selected)
    stats = BuildStats(
        requested=options.count,
        produced=len(selected),
        places_total=len(places),
        places_covered=len(covered),
        official=sum(1 for pano in selected if not pano.third_party),
        third_party=sum(1 for pano in selected if pano.third_party),
        countries=dict(countries.most_common()),
        skipped_places=skipped,
        warnings=warnings,
    )

    progress(Progress("done", len(selected), options.count, "Map ready"))
    return BuildResult(
        panos=selected,
        stats=stats,
        username=username,
        source_stats=source_stats or {},
    )
