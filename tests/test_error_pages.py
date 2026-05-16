"""HTML and JSON-shaped error responses from global handlers."""

from __future__ import annotations

from starlette.testclient import TestClient


def test_unknown_path_returns_friendly_html(client: TestClient) -> None:
    r = client.get("/zzz-nonexistent-route-999")
    assert r.status_code == 404
    assert "Page not found" in r.text
    assert "error-panel" in r.text


def test_http_exception_prefers_json_when_accept_application_json_only(client: TestClient) -> None:
    r = client.get("/zzz-nonexistent-route-998", headers={"Accept": "application/json"})
    assert r.status_code == 404
    assert r.headers.get("content-type", "").startswith("application/json")
    assert r.json()


def test_http_exception_healthz_not_found_still_json_for_json_client(client: TestClient) -> None:
    r = client.get("/healthz/not-a-child", headers={"Accept": "application/json"})
    assert r.status_code == 404
    payload = r.json()
    assert "detail" in payload
