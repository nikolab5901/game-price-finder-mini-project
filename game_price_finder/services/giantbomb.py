from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from game_price_finder.models import GameSummary

GIANT_BOMB_HEADERS = {"User-Agent": "GamePriceFinder/0.1 (respect GB limits)"}


def _release_year_any(orig: Any) -> int | None:
    if isinstance(orig, int) and 1900 <= orig <= 2100:
        return orig
    if isinstance(orig, str) and len(orig) >= 4:
        try:
            return int(orig[:4])
        except ValueError:
            return None
    return None


def summary_from_gb_game(payload: dict[str, Any]) -> GameSummary | None:
    guid = payload.get("guid")
    name = payload.get("name")
    if not guid or not name:
        return None
    img = payload.get("image")
    thumb = None
    if isinstance(img, dict):
        thumb = img.get("super_url") or img.get("medium_url")
    thumb_s = thumb if isinstance(thumb, str) else None

    plat_summary = None
    plats = payload.get("platforms")
    if isinstance(plats, list):
        names: list[str] = []
        for p in plats[:6]:
            if isinstance(p, dict) and p.get("name"):
                names.append(str(p["name"]))
        if names:
            plat_summary = ", ".join(names)
    elif isinstance(plats, str) and plats.strip():
        plat_summary = plats.strip()[:180]

    steam_raw = payload.get("steam_app_id") or payload.get("steam_appid")
    steam_id = None
    if steam_raw is not None:
        try:
            steam_id = int(str(steam_raw).strip())
        except ValueError:
            steam_id = None

    prov = []
    if thumb_s:
        prov.append("giantbomb:image")

    return GameSummary(
        igdb_id=None,
        giant_bomb_guid=str(guid),
        title=str(name),
        platform_summary=plat_summary,
        cover_image_url=thumb_s,
        release_year=_release_year_any(payload.get("original_release_date")),
        steam_app_id=steam_id,
        cover_sources=prov,
    )


async def giant_bomb_search_games(
    *,
    query: str,
    api_key: str,
    limit: int = 10,
    timeout: float = 25.0,
) -> list[GameSummary]:
    q = query.strip()
    if len(q) < 2 or not api_key.strip():
        return []
    params = {
        "api_key": api_key.strip(),
        "format": "json",
        "query": q,
        "resources": "game",
        "limit": str(min(limit, 15)),
    }
    async with httpx.AsyncClient(timeout=timeout, headers=GIANT_BOMB_HEADERS) as client:
        response = await client.get("https://www.giantbomb.com/api/search/", params=params)
        response.raise_for_status()
        payload = response.json()
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []

    summaries: list[GameSummary] = []
    for row in results[:limit]:
        if not isinstance(row, dict):
            continue
        guid = row.get("guid")
        name = row.get("name")
        if not guid or not name:
            continue
        img = row.get("image")
        thumb_s = None
        prov: list[str] = []
        if isinstance(img, dict):
            thumb_s = img.get("tiny_url") or img.get("thumb_url") or img.get("small_url")
            if isinstance(thumb_s, str):
                prov.append("giantbomb:thumb")
        summaries.append(
            GameSummary(
                igdb_id=None,
                giant_bomb_guid=str(guid),
                title=str(name),
                platform_summary=None,
                cover_image_url=thumb_s if isinstance(thumb_s, str) else None,
                release_year=_release_year_any(row.get("expected_release_year")),
                steam_app_id=None,
                cover_sources=prov,
            ),
        )
    return summaries


async def giant_bomb_get_game(
    *,
    guid: str,
    api_key: str,
    timeout: float = 25.0,
) -> GameSummary | None:
    if not api_key.strip() or not guid.strip():
        return None
    safe_guid = quote(guid.strip(), safe="-")
    params = {"api_key": api_key.strip(), "format": "json"}
    url = f"https://www.giantbomb.com/api/game/{safe_guid}/"
    async with httpx.AsyncClient(timeout=timeout, headers=GIANT_BOMB_HEADERS) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    game = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(game, dict):
        return None
    return summary_from_gb_game(game)
