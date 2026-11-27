# How been2guessr works

This document explains what the tool requests, how candidates are scored, and
where it can fail. It is meant for contributors and for anyone who wants to
fork the selection logic.

## 1. The two data sources

### BeenEverywhere

A public profile at `https://beeneverywhere.net/user/<username>` is a Svelte
app. The map points come from:

```
GET https://beeneverywhere.net/query-visits/<username>
```

which returns a GeoJSON `FeatureCollection`:

```json
{
  "type": "FeatureCollection",
  "features": [
    { "type": "Feature", "geometry": { "type": "Point", "coordinates": [0.0, 0.0] } }
  ],
  "stats": { "places_visited": 104, "un": { "GR": 86, "FR": 2 } }
}
```

`coordinates` is `[longitude, latitude]`. Private maps append a `?secret=…`
query parameter, which the tool forwards.

### Google Street View

GeoGuessr needs a panorama, not a coordinate. Google exposes two useful
internal endpoints to the Maps web client. They return plain JSON (with an
anti-hijack `)]}'` prefix) and require no API key.

| Purpose | Endpoint |
| --- | --- |
| Coverage in a zoom-17 tile | `google.com/maps/photometa/ac/v1?pb=…` |
| Nearest panorama to a point | `maps.googleapis.com/$rpc/…/SingleImageSearch` (POST) |
| Full metadata by pano ID | `google.com/maps/photometa/v1?pb=…` |

The request layouts are the ones used by the MIT-licensed
[`streetlevel`](https://github.com/sk-zk/streetlevel) project. been2guessr
vendors only the metadata subset in `src/been2guessr/panos.py`; it does not
depend on `streetlevel` or its heavier dependencies.

## 2. Candidate generation

For each visited place, in parallel:

1. Request the 3×3 block of zoom-17 coverage tiles centred on the place
   (one tile is roughly 250–300 m across at European latitudes).
2. Keep panos within `--max-radius` metres (default 1600 m).
3. If fewer than six candidates were found, request the surrounding ring
   (5×5).
4. If fewer than three candidates were found, run a nearest-panorama search at
   400 m, 1.2 km, and 4 km. This catches **trekker/scout** coverage that is not
   in the road tiles (gorge exits, beaches, trails).
5. If fewer than two candidates were found and photospheres are enabled, run
   the same search with `third_party=true`, then probe a 7×7 grid at ~400 m
   spacing so tiny islands can return more than one sphere.

Coverage tiles are cached per `(x, y)`, so nearby villages share requests.

## 3. Cleaning and ranking

Each place keeps a **spread pool** of up to 14 candidates:

- Sort by distance from the visited point.
- Greedily keep a candidate only if it is at least 190 m from everything
  already kept (260 m for very dense areas). If that yields fewer than five,
  relax to 90 m, then 40 m.
- This prevents a long straight road from contributing 14 near-identical
  panoramas.

The pool is then enriched with metadata. The following are discarded:

| Source | Why |
| --- | --- |
| `innerspace` | Indoor business-view tripods |
| `cultural_institute` | Indoor museum coverage |
| Dead pano IDs | Metadata lookup returns nothing |
| Third-party panos at a place with ≥2 official panos | Official coverage is more reliable and consistent |

Remaining candidates are scored:

```
score = distance_to_place
      + 220  if source != "launch"        # prefer car coverage
      + 900  if third-party               # prefer official
      + 150  if metadata is unavailable
      + (2016 - capture_year) * 25        # optional recent bias
```

Lower is better. Ties are broken by distance, then pano ID.

## 4. Balancing places

`allocate_targets()` is a pure function:

1. If the requested count is smaller than the number of places with coverage,
   give one location to the places with the most candidates.
2. Otherwise give every place `--per-place-min` locations.
3. Hand out the remainder round-robin, strongest places first, capped by
   `--per-place-max`.

This means a 300-location map from 104 places naturally lands at ~3 per place,
while a 50-location map samples the best-covered places instead of producing 50
pins around one city.

## 5. Global spacing

`select_global()` walks the ranked lists in rounds. A candidate is accepted
only if it is at least `--min-spacing` metres from every already-selected pano,
including picks belonging to other nearby places. If the build comes up short,
the process retries at 40% of the spacing, then at 1 m. IDs are always unique.

This is what stops a cluster of neighbouring villages from filling the map with
panoramas of the same junction.

## 6. Output

`geoguessr.py` writes:

```json
{
  "name": "user - Places I've Been (300)",
  "customCoordinates": [
    {
      "heading": 213,
      "pitch": 0,
      "zoom": 0,
      "panoId": "…",
      "countryCode": "<CC>",
      "stateCode": null,
      "lat": 0.0,
      "lng": 0.0
    }
  ]
}
```

This is the same shape GeoGuessr's map editor stores internally. The `panoId`
is what makes a handpicked location reproduce exactly. Headings are random but
seeded; pitch and zoom use the editor defaults.

A CSV report is generated on request with the place label, coordinates,
distance, coverage type, capture date, and a Google Maps permalink for each
pick.

## 7. Failure modes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| 404 from BeenEverywhere | Private map or typo | Add `?secret=…` or make the map public |
| Most requests fail / 403 | Google rate-limits the network | Wait a few minutes, lower `--concurrency` |
| Many places skipped | Sparse coverage | Raise `--max-radius`, enable photospheres |
| Fewer than requested | Not enough distinct coverage | Lower count or increase radius |
| A pano no longer plays | Google retired that ID | Rebuild the map |
| Labels look like regions | Pano address has no city component | Cosmetic only; it affects the CSV, not the JSON |

## 8. Privacy and etiquette

- The tool reads only the public map you point it at.
- It does not log usernames, coordinates, or generated maps to disk.
- Web jobs live in memory for `JOB_TTL_SECONDS` (default one hour).
- A 300-location build makes roughly 2,000 requests to Google. Do not run it in
  a tight loop, and keep public instances rate-limited.
