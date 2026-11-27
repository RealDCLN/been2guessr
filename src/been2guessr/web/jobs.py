"""In-memory job store for the web UI.

Jobs are intentionally ephemeral: a single process holds the result so the
download endpoint can serve it. Run the web app with one worker (the default in
the Docker image) or swap this store for Redis if you need to scale out.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from dataclasses import dataclass, field

from ..beeneverywhere import BeenEverywhereError
from ..geoguessr import to_csv, to_geoguessr
from ..models import BuildOptions, Progress
from ..panos import PanoError
from ..pipeline import BuildResult, build_from_source, summarize

log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    source: str
    options: BuildOptions
    status: str = "queued"  # queued | running | done | error
    stage: str = "queued"
    current: int = 0
    total: int = 0
    message: str = "Waiting for a worker"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    username: str | None = None
    result: BuildResult | None = None
    error: str | None = None

    def public(self) -> dict:
        payload = {
            "id": self.id,
            "status": self.status,
            "stage": self.stage,
            "current": self.current,
            "total": self.total,
            "message": self.message,
            "error": self.error,
            "elapsed_seconds": round(self.updated_at - self.created_at, 1),
        }
        if self.result is not None:
            payload["summary"] = summarize(self.result)
            payload["download"] = f"/api/jobs/{self.id}/download.json"
            payload["report"] = f"/api/jobs/{self.id}/report.csv"
            payload["points"] = [
                [round(pano.lat, 2), round(pano.lon, 2), pano.third_party] for pano in self.result.panos
            ]
            payload["preview"] = [
                {
                    "place": pano.place_label,
                    "country": pano.country_code,
                    "lat": round(pano.lat, 5),
                    "lng": round(pano.lon, 5),
                    "photosphere": pano.third_party,
                }
                for pano in self.result.panos[:6]
            ]
        return payload

    def json_bytes(self) -> bytes:
        assert self.result is not None
        import json

        payload = to_geoguessr(self.result, seed=self.options.seed)
        return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    def csv_text(self) -> str:
        assert self.result is not None
        return to_csv(self.result)


class JobStore:
    def __init__(
        self,
        *,
        max_concurrent: int = 2,
        ttl_seconds: int = 3600,
        rate_limit: int = 5,
        rate_window: int = 3600,
        max_locations: int = 2000,
    ) -> None:
        self.jobs: dict[str, Job] = {}
        self.max_concurrent = max_concurrent
        self.ttl_seconds = ttl_seconds
        self.rate_limit = rate_limit
        self.rate_window = rate_window
        self.max_locations = max_locations
        self._sem = asyncio.Semaphore(max(1, max_concurrent))
        self._starts: dict[str, list[float]] = {}

    # -- rate limiting ------------------------------------------------------
    def allow(self, ip: str) -> bool:
        now = time.time()
        starts = [stamp for stamp in self._starts.get(ip, []) if now - stamp < self.rate_window]
        if len(starts) >= self.rate_limit:
            self._starts[ip] = starts
            return False
        starts.append(now)
        self._starts[ip] = starts
        return True

    # -- lifecycle ----------------------------------------------------------
    def cleanup(self) -> None:
        cutoff = time.time() - self.ttl_seconds
        for job_id in [
            job_id
            for job_id, job in self.jobs.items()
            if job.updated_at < cutoff and job.status in ("done", "error")
        ]:
            self.jobs.pop(job_id, None)
        cutoff = time.time() - self.rate_window
        for ip in list(self._starts):
            self._starts[ip] = [stamp for stamp in self._starts[ip] if stamp >= cutoff]
            if not self._starts[ip]:
                self._starts.pop(ip, None)

    def create(self, source: str, options: BuildOptions) -> Job:
        job = Job(id=secrets.token_urlsafe(9), source=source, options=options)
        self.jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    async def run(self, job: Job) -> None:
        job.status = "queued"
        job.message = "Waiting for a worker"
        job.updated_at = time.time()

        async with self._sem:
            job.status = "running"
            job.message = "Contacting BeenEverywhere"
            job.updated_at = time.time()

            def on_progress(update: Progress) -> None:
                job.stage = update.stage
                job.current = update.current
                job.total = update.total
                job.message = update.message
                job.updated_at = time.time()

            try:
                result = await build_from_source(job.source, job.options, progress=on_progress)
                job.result = result
                job.username = result.username
                job.status = "done"
                job.stage = "done"
                job.current = len(result.panos)
                job.total = job.options.count
                job.message = "Your map is ready"
            except asyncio.CancelledError:
                job.status = "error"
                job.error = "Job cancelled."
                raise
            except (BeenEverywhereError, PanoError, ValueError) as exc:
                # These messages are written for users and contain no internals.
                log.warning("job %s failed: %s", job.id, exc)
                job.status = "error"
                job.error = str(exc) or exc.__class__.__name__
                job.message = "Build failed"
            except Exception:  # noqa: BLE001 - never leak internals to the client
                log.exception("job %s failed", job.id)
                job.status = "error"
                job.error = "The build failed unexpectedly. Please try again."
                job.message = "Build failed"
            finally:
                job.updated_at = time.time()
