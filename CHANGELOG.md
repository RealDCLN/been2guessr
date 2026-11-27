# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-27

### Added

- Python package `been2guessr` with a reusable build pipeline.
- CLI: `build`, `inspect`, and `serve`, with count, radius, spacing, per-place
  caps, photosphere toggles, seed, and CSV report options.
- Web UI: paste a username or profile URL, live progress, per-country summary,
  JSON/CSV downloads, and copy-to-clipboard.
- FastAPI backend with in-memory jobs, concurrency limits, per-IP rate limits,
  TTL cleanup, and health check.
- Minimal Street View client (coverage tiles, nearest panorama search,
  metadata by ID) with no API key and no heavy dependencies.
- Coverage fallbacks for trekker-only places and user photospheres.
- Balanced allocation across visited places and global spacing to avoid
  near-duplicates.
- GeoGuessr map JSON with pano IDs, coordinates, headings, and country codes.
- Dockerfile, Compose file, Render blueprint, and GitHub Actions CI.
- Unit tests for geometry, source parsing, panorama parsers, selection, output,
  and the web API.
- Documentation for the algorithm, deployment, and contribution workflow.
