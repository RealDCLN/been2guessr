from fastapi.testclient import TestClient

from been2guessr.web.app import create_app
from been2guessr.web.jobs import JobStore


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
