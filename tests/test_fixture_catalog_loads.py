"""Every bundled catalog fixture row must parse as GamePricingPage (CI guardrail)."""

from __future__ import annotations

import json
from pathlib import Path

from game_price_finder.models import GamePricingPage

PACKAGE_DIR = Path(__file__).resolve().parents[1] / "game_price_finder"

_CATALOG_JSON = ("demo_fixtures.json", "popular_catalog.json")


def test_fixture_json_rows_validate() -> None:
    for name in _CATALOG_JSON:
        path = PACKAGE_DIR / name
        assert path.is_file(), f"missing catalog file: {path}"
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = raw.get("entries", [])
        assert isinstance(entries, list), f"{name}: entries must be a list"
        for i, row in enumerate(entries):
            assert isinstance(row, dict), f"{name} entry {i}: must be object"
            GamePricingPage.model_validate(row)
