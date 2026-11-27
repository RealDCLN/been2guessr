"""FastAPI app: a small web UI around the build pipeline."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from .. import __version__
from ..beeneverywhere import BeenEverywhereError, parse_source
from ..geoguessr import filename
from ..models import BuildOptions
from .jobs import JobStore

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"


class BuildRequest(BaseModel):
    source: str = Field(min_length=1, max_length=300, description="Username or BeenEverywhere profile URL")
    count: int = Field(300, ge=1, le=10_000)
    max_radius_m: float = Field(1600, ge=100, le=20_000)
    min_spacing_m: float = Field(100, ge=0, le=10_000)
    per_place_min: int = Field(1, ge=0, le=50)
    per_place_max: int = Field(8, ge=1, le=100)
    include_photospheres: bool = True
    official_only: bool = False
    prefer_recent: bool = True
    seed: int | None = Field(None, ge=0, le=2**31 - 1)

    @model_validator(mode="after")
    def _check(self) -> BuildRequest:
        if self.per_place_max < self.per_place_min:
            raise ValueError("per_place_max must be >= per_place_min")
        return self


def _client_ip(request: Request) -> str:
    if os.getenv("TRUST_PROXY", "").lower() in ("1", "true", "yes"):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _cleanup_loop(store: JobStore) -> None:
    async def loop() -> None:
        while True:
            await asyncio.sleep(300)
            with contextlib.suppress(Exception):
                store.cleanup()

    return asyncio.create_task(loop())


def create_app(store: JobStore | None = None) -> FastAPI:
    store = store or JobStore(
        max_concurrent=int(os.getenv("MAX_CONCURRENT_JOBS", "2")),
        ttl_seconds=int(os.getenv("JOB_TTL_SECONDS", "3600")),
        rate_limit=int(os.getenv("RATE_LIMIT_JOBS", "5")),
        rate_window=int(os.getenv("RATE_LIMIT_WINDOW", "3600")),
        max_locations=int(os.getenv("MAX_BUILD_LOCATIONS", "2000")),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = _cleanup_loop(app.state.store)
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(
        title="been2guessr",
        version=__version__,
        description="Turn a BeenEverywhere travel map into a GeoGuessr custom map.",
        lifespan=lifespan,
    )
    app.state.store = store

    origins = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "").split(",") if origin.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index() -> HTMLResponse:
        return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "status": "ok",
            "version": __version__,
            "jobs": len(store.jobs),
            "max_locations": store.max_locations,
        }

    @app.post("/api/jobs", status_code=202)
    async def create_job(body: BuildRequest, request: Request) -> dict:
        try:
            parse_source(body.source)
        except BeenEverywhereError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if body.count > store.max_locations:
            raise HTTPException(
                status_code=400,
                detail=f"This server allows at most {store.max_locations} locations per map.",
            )
        if not store.allow(_client_ip(request)):
            raise HTTPException(
                status_code=429,
                detail="Too many maps from this address. Try again in a little while.",
            )

        options = BuildOptions(
            count=body.count,
            max_radius_m=body.max_radius_m,
            min_spacing_m=body.min_spacing_m,
            per_place_min=body.per_place_min,
            per_place_max=body.per_place_max,
            include_photospheres=body.include_photospheres and not body.official_only,
            official_only=body.official_only,
            prefer_recent=body.prefer_recent,
            seed=body.seed,
        )
        try:
            options.validate()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        job = store.create(body.source, options)
        asyncio.create_task(store.run(job))
        return {"id": job.id, "status": job.status}

    @app.get("/api/jobs/{job_id}")
    async def job_status(job_id: str) -> dict:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found (it may have expired).")
        return job.public()

    @app.get("/api/jobs/{job_id}/download.json")
    async def job_download(job_id: str) -> Response:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found (it may have expired).")
        if job.status != "done" or job.result is None:
            raise HTTPException(status_code=409, detail="The map is not ready yet.")
        name = filename(job.username, len(job.result.panos))
        return Response(
            job.json_bytes(),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    @app.get("/api/jobs/{job_id}/report.csv")
    async def job_report(job_id: str) -> Response:
        job = store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found (it may have expired).")
        if job.status != "done" or job.result is None:
            raise HTTPException(status_code=409, detail="The map is not ready yet.")
        name = filename(job.username, len(job.result.panos), "csv")
        return Response(
            job.csv_text(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    return app


app = create_app()
