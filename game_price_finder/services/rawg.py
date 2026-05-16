from __future__ import annotations

import re
from typing import Any

import httpx

from game_price_finder.models import GameSummary

RAWG_BASE = "https://api.rawg.io/api"
RAWG_HEADERS = {"User-Agent": "GamePriceFinder/0.1 (contact: none)"}

_STEAM_APP_RE = re.compile(r"(?:store\.steampowered\.com|steamcommunity\.com)/app/(\d+)", re.I)


def steam_app_id_from_rawg_game(payload: dict[str, Any]) -> int | None:
    stores = payload.get("stores")
    if not isinstance(stores, list):
        return None
    for row in stores:
        if not isinstance(row, dict):
            continue
        store = row.get("store")
        sid = None
        if isinstance(store, dict):
            sid = store.get("id")
        url = row.get("url_en") or row.get("url") or ""
        if isinstance(url, str):
            m = _STEAM_APP_RE.search(url)
            if m:
                try:
                    return int(m.group(1))
                except ValueError:
                    continue
        try:
            if int(sid) == 1 and isinstance(url, str):
                m = _STEAM_APP_RE.search(url)
                if m:
                    return int(m.group(1))
        except (TypeError, ValueError):
            continue
    return None


def _platform_summary_rawg(platforms: Any) -> str | None:
    if not isinstance(platforms, list) or not platforms:
        return None
    names: list[str] = []
    for p in platforms[:6]:
        if not isinstance(p, dict):
            continue
        inner = p.get("platform")
        if isinstance(inner, dict) and inner.get("name"):
            names.append(str(inner["name"]))
    return ", ".join(names) if names else None


def _release_year_rawg(released: Any) -> int | None:
    if not isinstance(released, str) or len(released) < 4:
        return None
    try:
        return int(released[:4])
    except ValueError:
        return None


def summary_from_rawg_search_row(row: dict[str, Any]) -> GameSummary | None:
    rid = row.get("id")
    name = row.get("name")
    if rid is None or not name:
        return None
    bg = row.get("background_image") if isinstance(row.get("background_image"), str) else None
    return GameSummary(
        igdb_id=None,
        rawg_id=int(rid),
        title=str(name),
        platform_summary=_platform_summary_rawg(row.get("platforms")),
        cover_image_url=bg,
        release_year=_release_year_rawg(row.get("released")),
        steam_app_id=None,
        cover_sources=["rawg:background"] if bg else [],
    )


async def rawg_search_games(
    *,
    query: str,
    api_key: str,
    limit: int = 15,
    timeout: float = 22.0,
) -> list[GameSummary]:
    q = query.strip()
    if len(q) < 2 or not api_key.strip():
        return []
    params = {"search": q, "page_size": str(min(limit, 40)), "key": api_key.strip()}
    async with httpx.AsyncClient(timeout=timeout, headers=RAWG_HEADERS) as client:
        response = await client.get(f"{RAWG_BASE}/games", params=params)
        response.raise_for_status()
        payload = response.json()
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        return []
    out: list[GameSummary] = []
    for row in results:
        if isinstance(row, dict):
            s = summary_from_rawg_search_row(row)
            if s:
                out.append(s)
    return out


async def rawg_get_game(
    *,
    rawg_id: int,
    api_key: str,
    timeout: float = 22.0,
) -> GameSummary | None:
    if not api_key.strip():
        return None
    params = {"key": api_key.strip()}
    async with httpx.AsyncClient(timeout=timeout, headers=RAWG_HEADERS) as client:
        response = await client.get(f"{RAWG_BASE}/games/{int(rawg_id)}", params=params)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        return None
    rid = payload.get("id")
    name = payload.get("name")
    if rid is None or not name:
        return None
    bg = payload.get("background_image_additional") or payload.get("background_image")
    bg_s = bg if isinstance(bg, str) else None
    steam = steam_app_id_from_rawg_game(payload)
    prov = ["rawg:background"] if bg_s else []
    if steam:
        prov.append("rawg:steam_store")
    return GameSummary(
        igdb_id=None,
        rawg_id=int(rid),
        title=str(name),
        platform_summary=_platform_summary_rawg(payload.get("platforms")),
        cover_image_url=bg_s,
        release_year=_release_year_rawg(payload.get("released")),
        steam_app_id=steam,
        cover_sources=prov,
    )
