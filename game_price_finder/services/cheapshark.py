from __future__ import annotations

from typing import Any

import httpx

from game_price_finder.models import GameSummary

CHEAPSHARK_BASE = "https://www.cheapshark.com/api/1.0"

CHEAPSHARK_HEADERS = {
    "User-Agent": "GamePriceFinder/0.1 (mini-project)",
    "Accept": "application/json",
}

_store_names_cache: dict[int, str] | None = None


def _cheapshark_client(*, timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, headers=CHEAPSHARK_HEADERS)


async def store_id_to_name(*, timeout: float = 20.0) -> dict[int, str]:
    global _store_names_cache
    if _store_names_cache is not None:
        return _store_names_cache
    async with _cheapshark_client(timeout=timeout) as client:
        response = await client.get(f"{CHEAPSHARK_BASE}/stores")
        response.raise_for_status()
        payload = response.json()
    mapping: dict[int, str] = {}
    if isinstance(payload, list):
        for row in payload:
            if not isinstance(row, dict):
                continue
            sid = row.get("storeID")
            name = row.get("storeName")
            try:
                mapping[int(sid)] = str(name) if name else f"Store {sid}"
            except (TypeError, ValueError):
                continue
    _store_names_cache = mapping
    return mapping


async def cheapshark_cheapest_for_steam_app_id(*, steam_app_id: int, timeout: float = 15.0) -> float | None:
    """Return CheapShark recorded cheapest PC deal price (USD) for a Steam app id, if known."""
    try:
        sid = int(steam_app_id)
    except (TypeError, ValueError):
        return None
    async with _cheapshark_client(timeout=timeout) as client:
        response = await client.get(f"{CHEAPSHARK_BASE}/games", params={"steamAppID": str(sid)})
        response.raise_for_status()
        payload = response.json()
    row: dict[str, Any] | None = None
    if isinstance(payload, dict):
        row = payload
    elif isinstance(payload, list) and payload:
        first = payload[0]
        row = first if isinstance(first, dict) else None
    if not row:
        return None
    cheapest = row.get("cheapest")
    if cheapest is None:
        return None
    try:
        return float(cheapest)
    except (TypeError, ValueError):
        return None


async def cheapshark_search_games(*, title: str, timeout: float = 25.0) -> list[dict[str, Any]]:
    q = title.strip()
    if len(q) < 2:
        return []
    async with _cheapshark_client(timeout=timeout) as client:
        response = await client.get(f"{CHEAPSHARK_BASE}/games", params={"title": q, "limit": "15"})
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


async def cheapshark_deals_for_game(*, cheapshark_game_id: int, page_size: int = 8, timeout: float = 25.0) -> list[dict[str, Any]]:
    async with _cheapshark_client(timeout=timeout) as client:
        response = await client.get(
            f"{CHEAPSHARK_BASE}/deals",
            params={"gameID": str(cheapshark_game_id), "pageSize": str(page_size)},
        )
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]


def pick_cheapshark_game_row(rows: list[dict[str, Any]], game: GameSummary) -> dict[str, Any] | None:
    if not rows:
        return None
    if game.steam_app_id is not None:
        target = int(game.steam_app_id)
        for row in rows:
            raw = row.get("steamAppID")
            try:
                if raw is not None and int(raw) == target:
                    return row
            except (TypeError, ValueError):
                continue
    return rows[0]


def deal_price_usd(deal: dict[str, Any]) -> float | None:
    for key in ("salePrice", "price"):
        raw = deal.get(key)
        if raw is None:
            continue
        try:
            return float(raw)
        except (TypeError, ValueError):
            continue
    return None


async def fetch_cheapshark_snapshot(game: GameSummary) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    rows = await cheapshark_search_games(title=game.title)
    picked = pick_cheapshark_game_row(rows, game)
    if not picked:
        return [], None
    cg_id = picked.get("gameID")
    try:
        cheapshark_game_id = int(cg_id)
    except (TypeError, ValueError):
        return [], None
    deals = await cheapshark_deals_for_game(cheapshark_game_id=cheapshark_game_id)
    return deals, picked
