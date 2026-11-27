import pytest
from fastapi.testclient import TestClient

from been2guessr.models import BuildOptions, BuildStats, Pano
from been2guessr.panos import PanoError
from been2guessr.selector import BuildResult
from been2guessr.web import jobs as jobs_module
from been2guessr.web.app import MAX_REQUEST_BYTES, create_app
from been2guessr.web.jobs import Job, JobStore


def make_client() -> TestClient:
    store = JobStore(rate_limit=100, max_locations=50)
    return TestClient(create_app(store))


def test_health():
    client = make_client()
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["max_locations"] == 50


def test_index():
    client = make_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "been2guessr" in response.text


def test_security_headers():
    client = make_client()
    response = client.get("/")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["content-security-policy"].startswith("default-src 'self'")
    assert "camera=()" in response.headers["permissions-policy"]
    assert "strict-transport-security" not in response.headers


def test_hsts_on_https_proxy():
    client = make_client()
    response = client.get("/", headers={"x-forwarded-proto": "https"})
    assert response.headers["strict-transport-security"].startswith("max-age=")


def test_rejects_oversized_body():
    client = make_client()
    response = client.post(
        "/api/jobs",
        content=b"{" + b" " * MAX_REQUEST_BYTES + b"}",
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 413


def test_robots():
    client = make_client()
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "Allow: /" in response.text


def test_humans():
    client = make_client()
    response = client.get("/humans.txt")
    assert response.status_code == 200
    assert "DCLN" in response.text


def test_rejects_invalid_source():
    client = make_client()
    response = client.post("/api/jobs", json={"source": "https://example.com/nope", "count": 10})
    assert response.status_code == 400
    assert "BeenEverywhere" in response.json()["detail"]


def test_rejects_too_many_locations():
    client = make_client()
    response = client.post("/api/jobs", json={"source": "example-user", "count": 51})
    assert response.status_code == 400


def test_unknown_job():
    client = make_client()
    assert client.get("/api/jobs/nope").status_code == 404


def test_public_job_includes_coverage_points():
    result = BuildResult(
        panos=[
            Pano(id="a", lat=1.234, lon=2.345),
            Pano(id="b", lat=-3.456, lon=-4.567, third_party=True),
        ],
        stats=BuildStats(
            requested=2,
            produced=2,
            places_total=2,
            places_covered=2,
            official=1,
            third_party=1,
            countries={"PT": 2},
            skipped_places=[],
            warnings=[],
        ),
        username="tester",
    )
    job = Job(id="job", source="tester", options=BuildOptions(count=2))
    job.result = result

    payload = job.public()

    assert payload["summary"]["produced"] == 2
    assert payload["points"] == [[1.23, 2.35, False], [-3.46, -4.57, True]]


@pytest.mark.asyncio
async def test_job_surfaces_known_errors(monkeypatch):
    async def fail(*args, **kwargs):
        raise PanoError("Google refused the panorama request (403). Try again later.")

    monkeypatch.setattr(jobs_module, "build_from_source", fail)
    store = JobStore(rate_limit=100)
    job = store.create("tester", BuildOptions(count=1))
    await store.run(job)

    assert job.status == "error"
    assert "403" in job.error


@pytest.mark.asyncio
async def test_job_hides_unexpected_errors(monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError("internal path /tmp/secret")

    monkeypatch.setattr(jobs_module, "build_from_source", fail)
    store = JobStore(rate_limit=100)
    job = store.create("tester", BuildOptions(count=1))
    await store.run(job)

    assert job.status == "error"
    assert job.error == "The build failed unexpectedly. Please try again."
