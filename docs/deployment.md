# Deploying the web UI

The web app is a single FastAPI process. Builds run as asyncio background
tasks; the result is held in memory and served from
`/api/jobs/<id>/download.json`.

> **Run one worker.** Because jobs are stored in process memory, multiple
> Uvicorn/Gunicorn workers would make a job created on worker A invisible to a
> download request handled by worker B. One worker can handle several builds
> concurrently (see `MAX_CONCURRENT_JOBS`).

## Docker

```bash
docker compose up --build
```

Then open <http://127.0.0.1:8000>.

Or without Compose:

```bash
docker build -t been2guessr .
docker run --rm -p 8000:8000 \
  -e MAX_CONCURRENT_JOBS=2 \
  -e MAX_BUILD_LOCATIONS=2000 \
  been2guessr
```

The image runs as a non-root user and includes a container health check against
`/api/health`.

## Render

1. Push the repository to GitHub.
2. In Render: **New → Blueprint**, pick the repo. `render.yaml` is detected.
3. Deploy. The free plan is fine for personal use; it sleeps when idle.

If you prefer manual setup: create a **Web Service** from the Dockerfile,
health check path `/api/health`, and add the environment variables below.

## Fly.io

```bash
fly launch --no-deploy
fly scale count 1
fly deploy
```

Set `internal_port = 8000` in `fly.toml` if Fly did not infer it. Keep one
machine; the in-memory job store is per instance.

## Railway / Heroku-style hosts

Use the Dockerfile. Expose port `8000`. Set `PORT` only if your platform
requires it, and start with:

```bash
been2guessr serve --host 0.0.0.0 --port ${PORT:-8000}
```

## Environment variables

| Variable | Default | Notes |
| --- | --- | --- |
| `MAX_CONCURRENT_JOBS` | `2` | Concurrent builds. Each build uses ~2,000 requests. |
| `MAX_BUILD_LOCATIONS` | `2000` | Reject larger requests before doing work. |
| `JOB_TTL_SECONDS` | `3600` | Time a finished job stays downloadable. |
| `RATE_LIMIT_JOBS` | `5` | Jobs per IP per window. |
| `RATE_LIMIT_WINDOW` | `3600` | Window length in seconds. |
| `TRUST_PROXY` | `false` | Set to `true` behind a reverse proxy so rate limits use `X-Forwarded-For`. |
| `ALLOWED_ORIGINS` | empty | Comma-separated CORS origins if you embed the API. |

## Reverse proxy

Any proxy works. Two things matter:

1. Forward the real client IP and set `TRUST_PROXY=true` if you rely on
   per-IP rate limits.
2. Do not add a short read timeout that kills idle connections while a build is
   polling. The UI polls every 1.2 s, so a 60 s proxy timeout is plenty.

Caddy example:

```caddy
map.example.com {
    reverse_proxy 127.0.0.1:8000 {
        header_up X-Forwarded-For {remote_host}
    }
}
```

Nginx example:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_read_timeout 90s;
}
```

## Resource usage

A 300-location build:

- ~1,000–2,500 Google requests, depending on candidate density;
- ~100–150 MB RAM in the Python process (plus FastAPI overhead);
- 1–4 minutes on a normal connection, mostly waiting on Google.

The free Render instance can handle a build, but a 512 MB instance is tight if
two builds run at once. Leave `MAX_CONCURRENT_JOBS=1` on small hosts.

## Scaling out

If you need multiple instances, replace `JobStore` with a shared store:

- Persist `Job` records and the generated JSON in Redis/S3.
- Use a task queue (RQ, Celery, Arq) for builds.
- Keep the download endpoint stateless.

The rest of the app (pipeline, selector, serialiser) is already independent of
the web layer.
