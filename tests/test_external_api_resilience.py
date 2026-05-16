"""Upstream failures must not collapse fixture game detail pages to 500."""

from __future__ import annotations

import httpx
import pytest
from starlette.testclient import TestClient


@pytest.fixture()
def patched_cheapshark_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(*, title: str, timeout: float = 25.0) -> list[dict[str, object]]:
        del title, timeout
        raise httpx.ConnectError("simulated CheapShark outage", request=None)

    monkeypatch.setattr("game_price_finder.services.cheapshark.cheapshark_search_games", _boom)


def test_fixture_game_detail_survives_cheapshark_error(
    client: TestClient,
    patched_cheapshark_failure: object,
) -> None:
    r = client.get("/games/900001")
    assert r.status_code == 200
    body = r.text.lower()
    assert "internal server error" not in body
