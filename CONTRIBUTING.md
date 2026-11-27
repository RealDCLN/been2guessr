# Contributing

Thanks for helping! been2guessr is a small, dependency-light project.

## Setup

```bash
git clone https://github.com/your-username/been2guessr
cd been2guessr
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

## Checks

```bash
ruff check .
pytest -q
```

Please keep tests network-free. The panorama parsers are tested with small
hand-built arrays that mirror Google's response shape.

## What to work on

Good first issues:

- More place labels (offline city lookup, or an optional Nominatim mode).
- A map preview (Leaflet) showing the selected pins before download.
- A GeoGuessr map export that also writes tags for map-making.app.
- Better handling of private maps and expired secrets.
- Apple Look Around support, if you are feeling brave.

## Code style

- Python 3.10+, type hints on public functions.
- Pure logic in `selector.py` should stay testable without `httpx`.
- Keep the web layer thin; put build behaviour in `pipeline.py`.
- No new runtime dependencies unless they replace a lot of code. The project
  deliberately avoids `streetlevel`, `pandas`, and browser automation.

## Changing the panorama client

Google's internal response arrays are positional and occasionally shift. When
you touch `panos.py`:

1. Keep the defensive `_get` / `_dig` accessors.
2. Add or update a fixture-shaped unit test for every new path.
3. Manually verify one official pano and one photosphere.
4. Document any new endpoint in `docs/how-it-works.md`.

## Pull requests

- One logical change per PR.
- Include a test for bug fixes.
- Update `README.md` / `docs/` when behaviour or flags change.
- Do not commit generated maps, API keys, or personal BeenEverywhere data.
- Be kind in reviews.

## Reporting bugs

Open an issue with:

- the command or request you ran (redact your username if you want);
- the error text;
- Python version and OS;
- whether the map is public or uses a secret.

Security issues: see [SECURITY.md](SECURITY.md).
