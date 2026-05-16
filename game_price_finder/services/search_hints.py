from __future__ import annotations

import asyncio

from rapidfuzz import fuzz, process

from game_price_finder.models import GameSummary, SearchSuggestion
from game_price_finder.services.cheapshark import cheapshark_cheapest_for_steam_app_id
from game_price_finder.services.steam import steam_store_search

DEFAULT_FUZZ_THRESHOLD = 72
IGDB_WEAK_RESULT_CAP = 3
DEFAULT_SUGGESTION_LIMIT = 6


async def fuzzy_search_suggestions(
    *,
    query: str,
    threshold: int = DEFAULT_FUZZ_THRESHOLD,
    limit: int = DEFAULT_SUGGESTION_LIMIT,
    steam_timeout: float = 18.0,
) -> list[SearchSuggestion]:
    q = query.strip()
    if len(q) < 2:
        return []

    items = await steam_store_search(term=q, timeout=steam_timeout)
    titles: list[str] = []
    for row in items:
        name = row.get("name")
        if isinstance(name, str):
            cleaned = name.strip()
            if cleaned:
                titles.append(cleaned)
    if not titles:
        return []

    extracted = process.extract(q, titles, scorer=fuzz.WRatio, limit=limit)
    out: list[SearchSuggestion] = []
    seen: set[str] = set()
    for title, score, _idx in extracted:
        if score < threshold:
            continue
        key = title.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(SearchSuggestion(title=title, suggested_query=title))
    return out


async def maybe_fuzzy_suggestions(
    *,
    query: str,
    igdb_hit_count: int,
    threshold: int = DEFAULT_FUZZ_THRESHOLD,
    limit: int = DEFAULT_SUGGESTION_LIMIT,
) -> list[SearchSuggestion]:
    if igdb_hit_count >= IGDB_WEAK_RESULT_CAP:
        return []
    return await fuzzy_search_suggestions(query=query, threshold=threshold, limit=limit)


async def batch_price_hints_for_games(
    games: list[GameSummary],
    *,
    concurrency: int = 8,
    overall_timeout: float = 12.0,
    per_game_timeout: float = 14.0,
) -> dict[int, float]:
    """Best-effort CheapShark cheapest prices keyed by IGDB id (Steam-linked rows only)."""
    targets = [g for g in games if g.steam_app_id is not None]
    if not targets:
        return {}

    sem = asyncio.Semaphore(concurrency)

    async def fetch_price(game: GameSummary) -> tuple[int, float | None]:
        assert game.steam_app_id is not None
        async with sem:
            try:
                price = await cheapshark_cheapest_for_steam_app_id(
                    steam_app_id=int(game.steam_app_id),
                    timeout=per_game_timeout,
                )
            except Exception:
                return game.igdb_id, None
            return game.igdb_id, price

    async def run_all() -> dict[int, float]:
        pairs = await asyncio.gather(*(fetch_price(g) for g in targets))
        hints: dict[int, float] = {}
        for igdb_id, price in pairs:
            if price is not None:
                hints[igdb_id] = price
        return hints

    try:
        async with asyncio.timeout(overall_timeout):
            return await run_all()
    except TimeoutError:
        return {}

