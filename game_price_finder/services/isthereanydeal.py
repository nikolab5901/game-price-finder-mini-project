from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

ITAD_BASE = "https://api.isthereanydeal.com"
# Steam storefront id inside ITAD lookups (confirmed in upstream OpenAPI examples).
ITAD_STEAM_SHOP_ID = 61

_ITAD_HEADERS = {
    "User-Agent": "GamePriceFinder/0.1 (mini-project)",
    "Accept": "application/json",
}


def _itad_client(*, timeout: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout, headers=_ITAD_HEADERS)


def parse_history_timestamp(value: Any) -> datetime | None:
    """ISO-8601 instant from `/games/history/v2`."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def history_row_sale_price(row: dict[str, Any]) -> tuple[float | None, str]:
    """Return (sale_amount, uppercase currency) when present."""
    deal = row.get("deal") if isinstance(row.get("deal"), dict) else None
    if not deal:
        return None, "USD"
    price = deal.get("price") if isinstance(deal.get("price"), dict) else None
    if not price:
        return None, "USD"
    amt = price.get("amount")
    curr = price.get("currency")
    cc = str(curr).upper() if curr else ""
    try:
        val = float(amt) if amt is not None else None
    except (TypeError, ValueError):
        val = None
    return val, cc or "USD"


def _parsed_uuid_candidate(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip()
    try:
        UUID(s)
        return s
    except ValueError:
        return None


async def lookup_itad_uuid_for_steam_app(
    *,
    steam_app_id: int,
    api_key: str,
    timeout: float = 28.0,
) -> str | None:
    """Resolve IsThereAnyDeal game UUID for a Steam `app/` id."""
    app_key = f"app/{int(steam_app_id)}"
    url = f"{ITAD_BASE}/lookup/id/shop/{ITAD_STEAM_SHOP_ID}/v1"
    params = {"key": api_key}
    payload = [app_key]
    async with _itad_client(timeout=timeout) as client:
        response = await client.post(url, params=params, json=payload)
        response.raise_for_status()
        mapping = response.json()
    if not isinstance(mapping, dict):
        return None
    mapped = mapping.get(app_key)
    rid = _parsed_uuid_candidate(mapped)
    if rid:
        return rid
    alt: str | None = None
    for k, v in mapping.items():
        if isinstance(k, str) and k.startswith(f"app/{int(steam_app_id)}"):
            alt = _parsed_uuid_candidate(v) or alt
    return alt


async def fetch_price_history_log(
    *,
    game_uuid: str,
    api_key: str,
    country: str = "US",
    since: datetime | None = None,
    timeout: float = 35.0,
) -> list[dict[str, Any]]:
    """Raw history rows from ITAD `GET /games/history/v2`."""
    url = f"{ITAD_BASE}/games/history/v2"
    params: dict[str, Any] = {
        "key": api_key,
        "id": game_uuid,
        "country": country,
    }
    if since is not None:
        s = since if since.tzinfo else since.replace(tzinfo=UTC)
        params["since"] = s.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    async with _itad_client(timeout=timeout) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):
        return []
    return [row for row in payload if isinstance(row, dict)]
