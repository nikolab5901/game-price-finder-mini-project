"""Pytest configuration: settings override for deterministic fixture/catalog tests."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from game_price_finder.config import Settings, get_settings
from game_price_finder.main import app, settings_dep


@pytest.fixture(autouse=True)
def override_app_settings(tmp_path: Path) -> Generator[None, None, None]:
    """Use fixture catalog only; writable SQLite path per test run."""

    def _deps() -> Settings:
        return Settings(use_fixtures=True, feedback_db_path=str(tmp_path / "feedback_autouse.db"))

    get_settings.cache_clear()
    app.dependency_overrides[settings_dep] = _deps
    yield
    app.dependency_overrides.pop(settings_dep, None)
    get_settings.cache_clear()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)

