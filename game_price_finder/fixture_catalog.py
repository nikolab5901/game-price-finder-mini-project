from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from game_price_finder.models import GamePricingPage, GameSummary

_PACKAGE_DIR = Path(__file__).resolve().parent
# demo_fixtures.json first so synthetic demos appear before curated titles on empty browse.
_FIXTURE_JSON_PATHS = (
    _PACKAGE_DIR / "demo_fixtures.json",
    _PACKAGE_DIR / "popular_catalog.json",
)


@lru_cache
def _catalog_pages() -> tuple[GamePricingPage, ...]:
    pages: list[GamePricingPage] = []
    for path in _FIXTURE_JSON_PATHS:
        if not path.is_file():
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = raw.get("entries", [])
        for row in entries:
            if isinstance(row, dict):
                pages.append(GamePricingPage.model_validate(row))
    return tuple(pages)


def fixture_search(query: str, *, limit: int = 20) -> list[GameSummary]:
    pages = _catalog_pages()
    q = query.strip().lower()
    if not q:
        return [p.game for p in pages[:limit]]
    hits = [p.game for p in pages if q in p.game.title.lower() or q in (p.game.platform_summary or "").lower()]
    return hits[:limit]


def fixture_detail(igdb_id: int) -> GamePricingPage | None:
    for page in _catalog_pages():
        if page.game.igdb_id == igdb_id:
            return page
    return None
