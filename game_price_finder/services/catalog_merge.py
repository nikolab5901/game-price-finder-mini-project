from __future__ import annotations

import asyncio

from game_price_finder.models import GameSummary
from game_price_finder.services.giantbomb import giant_bomb_search_games
from game_price_finder.services.rawg import rawg_search_games

DEFAULT_MERGE_MAX_RESULTS = 40
MAX_MERGED_RESULTS = DEFAULT_MERGE_MAX_RESULTS  # backward-compatible alias


def normalize_title(title: str) -> str:
    return " ".join(title.lower().split())


def ensure_catalog_nav_urls(game: GameSummary) -> GameSummary:
    dp = game.detail_path
    hk = game.price_hint_key
    if not dp:
        if game.igdb_id is not None:
            dp = f"/games/{game.igdb_id}"
        elif game.rawg_id is not None:
            dp = f"/games/rawg/{game.rawg_id}"
        elif game.giant_bomb_guid:
            from urllib.parse import quote as urlquote

            dp = f"/games/giantbomb/{urlquote(game.giant_bomb_guid, safe='')}"
    if not hk:
        if game.igdb_id is not None:
            hk = f"igdb:{game.igdb_id}"
        elif game.steam_app_id is not None:
            hk = f"steam:{game.steam_app_id}"
    return game.model_copy(update={"detail_path": dp, "price_hint_key": hk})


def dedupe_supplemental(primary: list[GameSummary], candidates: list[GameSummary]) -> list[GameSummary]:
    titles = {normalize_title(g.title) for g in primary}
    steams = {g.steam_app_id for g in primary if g.steam_app_id is not None}
    rawg_ids = {g.rawg_id for g in primary if g.rawg_id is not None}
    gb_guids = {g.giant_bomb_guid for g in primary if g.giant_bomb_guid}

    out: list[GameSummary] = []
    for g in candidates:
        if normalize_title(g.title) in titles:
            continue
        if g.steam_app_id is not None and g.steam_app_id in steams:
            continue
        if g.rawg_id is not None and g.rawg_id in rawg_ids:
            continue
        if g.giant_bomb_guid and g.giant_bomb_guid in gb_guids:
            continue
        out.append(g)
        titles.add(normalize_title(g.title))
        if g.steam_app_id is not None:
            steams.add(g.steam_app_id)
        if g.rawg_id is not None:
            rawg_ids.add(g.rawg_id)
        if g.giant_bomb_guid:
            gb_guids.add(g.giant_bomb_guid)
    return out


async def merge_catalog_search(
    *,
    query: str,
    primary_rows: list[GameSummary],
    rawg_api_key: str | None,
    giant_bomb_api_key: str | None,
    rawg_limit: int = 15,
    gb_limit: int = 8,
    merge_max: int = DEFAULT_MERGE_MAX_RESULTS,
) -> list[GameSummary]:
    candidates: list[GameSummary] = []

    async def safe_rawg() -> list[GameSummary]:
        if not rawg_api_key:
            return []
        try:
            return await rawg_search_games(query=query, api_key=rawg_api_key, limit=rawg_limit)
        except Exception:
            return []

    async def safe_gb() -> list[GameSummary]:
        if not giant_bomb_api_key:
            return []
        try:
            return await giant_bomb_search_games(query=query, api_key=giant_bomb_api_key, limit=gb_limit)
        except Exception:
            return []

    rawg_rows, gb_rows = await asyncio.gather(safe_rawg(), safe_gb())
    candidates.extend(rawg_rows)
    candidates.extend(gb_rows)

    extra = dedupe_supplemental(primary_rows, candidates)
    merged = primary_rows + extra
    merged = merged[:merge_max]
    return [ensure_catalog_nav_urls(g) for g in merged]
