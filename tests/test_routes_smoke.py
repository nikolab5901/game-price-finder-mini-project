"""High-level routes return expected status with fixture-backed settings."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_smoke_public_routes(client: TestClient) -> None:
    for path in ("/", "/search", "/guides", "/healthz"):
        r = client.get(path)
        assert r.status_code == 200, path

    r = client.get("/games/900001")
    assert r.status_code == 200
