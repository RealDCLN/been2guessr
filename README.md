# been2guessr

[![CI](https://github.com/RealDCLN/been2guessr/actions/workflows/ci.yml/badge.svg)](https://github.com/RealDCLN/been2guessr/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-8ef0a3.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-5cc8ff.svg)](pyproject.toml)

Turn a [BeenEverywhere](https://beeneverywhere.net) travel map into a playable
[GeoGuessr](https://www.geoguessr.com) custom map.

Paste a public BeenEverywhere profile and get a JSON file of real Street View
panoramas near the places you have visited — with pano IDs, coordinates, and
starting headings, ready to import as handpicked locations.

```
BeenEverywhere map  →  Street View coverage search  →  balanced selection  →  GeoGuessr JSON
```

## Why this exists

BeenEverywhere gives you a beautiful map of everywhere you have been, but it
only stores coordinates. GeoGuessr needs actual panoramas, one per location,
and a map with 300 pins in the same three streets is not fun. been2guessr:

- reads the public GeoJSON behind a BeenEverywhere profile;
- finds official Street View coverage around every visited place;
- falls back to real user photospheres where Google never drove (small islands,
  mountain villages, beaches);
- drops indoor/business panoramas, broken IDs, and near-duplicates;
- spreads picks across **all** your places with a configurable minimum spacing;
- writes the exact JSON shape the GeoGuessr map editor imports.

## Quick start

### Web UI

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
been2guessr serve
```

Open <http://127.0.0.1:8000>, paste a username or profile URL, choose how many
locations you want, and download the result. The UI shows live progress and a
per-country summary.

### CLI

```bash
been2guessr build your-username -n 300 -o my-map.json --csv
```

Or use a full profile URL:

```bash
been2guessr build "https://beeneverywhere.net/user/your-username" -n 300
```

`--csv` also writes a report with the place name, pano ID, capture date, and a
Google Maps link for every pick, so you can review the map before importing.

### Inspect a map first

```bash
been2guessr inspect your-username
```

Prints the number of places, the country breakdown, and the map's extreme
points without building anything.

## Installation

```bash
pip install been2guessr
```

Requires Python 3.10+. The only runtime dependencies are `httpx`, `fastapi`,
and `uvicorn`.

## CLI options

| Option | Default | Description |
| --- | --- | --- |
| `-n, --count` | `300` | Number of locations to generate |
| `-o, --output` | `{user}-geoguessr-{n}.json` | Output file |
| `--csv` | off | Also write a CSV report |
| `--array` | off | Write a bare location array instead of the map object |
| `--max-radius` | `1600` | Search radius around each place, in metres |
| `--min-spacing` | `100` | Minimum distance between selected panoramas, in metres |
| `--per-place-min` | `1` | Minimum picks per visited place |
| `--per-place-max` | `8` | Maximum picks per visited place |
| `--official-only` | off | Never use user photospheres |
| `--no-photospheres` | off | Alias for `--official-only` |
| `--no-recent-bias` | off | Do not prefer newer captures |
| `--seed` | random | Seed for starting headings (reproducible output) |
| `--concurrency` | `12` | Parallel request limit |
| `--input FILE` | — | Build from a saved `/query-visits` JSON file |
| `-q, --quiet` | off | Only print the final summary |

Examples:

```bash
# A small map for testing
been2guessr build your-username -n 50 -o test.json --csv

# Official coverage only, tighter search
been2guessr build your-username -n 200 --official-only --max-radius 800

# Reproducible headings
been2guessr build your-username -n 300 --seed 42 -o map.json

# Build from a JSON file you saved earlier
been2guessr build --input query-visits.json -n 300
```

## Output format

The main file looks like a GeoGuessr map draft:

```json
{
  "name": "your-username - Places I've Been (300)",
  "customCoordinates": [
    {
      "heading": 213,
      "pitch": 0,
      "zoom": 0,
      "panoId": "<pano-id>",
      "countryCode": "<ISO-3166-1 alpha-2>",
      "stateCode": null,
      "lat": 0.0,
      "lng": 0.0
    }
  ]
}
```

Import it in the GeoGuessr map editor with **Import locations**. If your
importer only accepts a bare array, use `--array`.

## How it works

1. **Places** — `GET https://beeneverywhere.net/query-visits/<username>`
   returns a GeoJSON `FeatureCollection` of visited points.
2. **Coverage** — for each place, been2guessr reads Google's zoom-17 Street
   View coverage tiles, then expands outward when a place is sparse. Remote
   places use a point search so trekker coverage (gorge exits, beaches) is not
   missed.
3. **Metadata** — candidates are read in bulk. Indoor panoramas
   (`innerspace`, `cultural_institute`), dead IDs, and user photospheres at
   places that already have official coverage are filtered out.
4. **Selection** — each place gets a spread-out candidate pool. A round-robin
   allocator gives every place a fair share and hands leftovers to places with
   more coverage, capped by `--per-place-max`. A global spacing check prevents
   two picks from landing on top of each other, even across nearby places.
5. **Output** — every pick keeps its original pano ID and coordinates, so
   GeoGuessr plays the exact panorama that was chosen.

The panorama API is the same internal one Google Maps uses. It needs no API
key, but it is unofficial and can change without notice. See
[docs/how-it-works.md](docs/how-it-works.md) for the details and failure modes.

## Deploying the web UI

The app is a normal FastAPI service with one important constraint: jobs are
held in memory, so run **one worker**. For a personal or small public instance
that is plenty.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/RealDCLN/been2guessr)

The free, step-by-step path is **[docs/deploy-render.md](docs/deploy-render.md)**:
GitHub → Render Blueprint → free `onrender.com` URL, with automatic deploys on
every push. No credit card is normally required.

> Netlify, Vercel, and Cloudflare Workers are built for short requests. A build
> makes ~2,000 outbound requests and takes 2–4 minutes, so it does not fit their
> free function limits. Use a Docker web host instead.

### Docker

```bash
docker compose up --build
```

Open <http://127.0.0.1:8000>.

### Render / Railway / Fly.io

A `render.yaml` is included. Point any Docker-based host at the repository; the
container listens on the platform's `PORT` (falling back to 8000) and exposes a
`/api/health` check.

Environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `MAX_CONCURRENT_JOBS` | `2` | Builds allowed to run at once |
| `MAX_BUILD_LOCATIONS` | `2000` | Per-map location cap |
| `JOB_TTL_SECONDS` | `3600` | How long finished jobs stay downloadable |
| `RATE_LIMIT_JOBS` | `5` | Jobs per IP per window |
| `RATE_LIMIT_WINDOW` | `3600` | Rate-limit window in seconds |
| `TRUST_PROXY` | `false` | Trust `X-Forwarded-For` for client IPs (set `true` on Render) |
| `ALLOWED_ORIGINS` | empty | Comma-separated CORS origins, if embedding |

See [docs/deployment.md](docs/deployment.md) for reverse-proxy and scaling
notes, and [docs/deploy-render.md](docs/deploy-render.md) for the full free
walkthrough.

## Development

```bash
git clone https://github.com/RealDCLN/been2guessr
cd been2guessr
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

pytest
ruff check .
```

Project layout:

```
src/been2guessr/
  beeneverywhere.py   # username parsing + public GeoJSON client
  panos.py            # minimal Google Street View panorama client
  selector.py         # coverage search, quality filters, allocation
  geoguessr.py        # JSON/CSV serialisation
  pipeline.py         # shared build entry points
  cli.py              # argparse CLI
  web/                # FastAPI app + static UI
tests/                # unit tests, no network required
docs/                 # algorithm + deployment notes
```

## Notes and limitations

- **Public maps only.** Private BeenEverywhere maps can be used by passing the
  `?secret=...` from the profile URL.
- **Coverage is not universal.** Some tiny islands and remote valleys have no
  Street View at all. The build skips them and reports how many places were
  covered. Turn on photospheres to catch more.
- **Unofficial endpoints.** Google can change or rate-limit them. If most
  requests fail, wait a few minutes and retry with a lower `--concurrency`.
- **Pano IDs can be retired.** Google occasionally removes imagery. The
  selector reads current metadata, but a map built today may lose a location
  months from now.
- **Rate limits.** For public deployments keep `MAX_CONCURRENT_JOBS` low. Each
  300-location build makes roughly 2,000 requests to Google.
- **Privacy.** The tool only reads the public map you point it at. It does not
  store usernames or results beyond the in-memory job cache.

## Publishing your own copy

This repository is linked to **RealDCLN** on GitHub and branded **DCLN**. If
you fork it and want the links to point at your account:

```bash
python scripts/personalize.py --from RealDCLN <your-github-username>
git add -A
git commit -m "Point links at my account"
```

The example commands and the username field stay generic on purpose.

Then push. If you are starting from a copy without git history:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-github-username>/been2guessr.git
git push -u origin main
```

GitHub Actions runs lint, tests, and a Docker build on every push. The Render
blueprint is optional; see [docs/deployment.md](docs/deployment.md).

## Legal

This is an unofficial hobby project. It is not affiliated with GeoGuessr,
Google, or BeenEverywhere. Google Street View imagery remains subject to
Google's terms; use the generated maps for personal, non-commercial play.
BeenEverywhere map data belongs to its users — only build maps from profiles
you have permission to use.

## Credits

Built by [DCLN](https://github.com/RealDCLN). Panorama request layouts were adapted
from the MIT-licensed [streetlevel](https://github.com/sk-zk/streetlevel)
project — see [NOTICE](NOTICE) for attribution.

## License

MIT. See [LICENSE](LICENSE).

---

<p align="center">
  <a href="https://github.com/RealDCLN">
    <img src="assets/made-by-dcln.svg" alt="made by DCLN" height="44" />
  </a>
</p>
