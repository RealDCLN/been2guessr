# Security policy

## Supported versions

The latest release on the `main` branch is supported.

## Reporting a vulnerability

Please do not open a public issue for security problems. Email the maintainer
or use GitHub's private vulnerability reporting on the repository. Include:

- what the issue is;
- steps to reproduce;
- impact (e.g. SSRF, denial of service, data exposure);
- any suggested fix.

You will get an acknowledgement within a few days.

## Scope

been2guessr is a small self-hostable app. Areas worth reviewing:

- **Source parsing** — the web API accepts a username or BeenEverywhere URL.
  Only `beeneverywhere.net/user/<name>` is fetched; no arbitrary URLs.
- **Rate limiting** — per-IP limits are in memory and reset on restart. Put a
  reverse proxy in front of a public instance if you need stronger protection.
- **Resource use** — one build can make thousands of outbound requests. Keep
  `MAX_CONCURRENT_JOBS` and `MAX_BUILD_LOCATIONS` conservative.
- **Downloads** — job IDs are random (`secrets.token_urlsafe`). Results are
  readable by anyone with the ID until they expire. Do not treat them as
  private storage.
- **Dependencies** — keep `httpx`, `fastapi`, and `uvicorn` up to date.

## Out of scope

- Google or GeoGuessr changing/removing their endpoints.
- Rate limits imposed by Google on your network.
- The accuracy of BeenEverywhere data.
- Maps built from profiles you do not have permission to use.
