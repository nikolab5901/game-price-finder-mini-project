from __future__ import annotations

import logging
import re
from typing import Any, Literal

import httpx

from game_price_finder.models import GameSummary

STEAM_STORE_SEARCH = "https://store.steampowered.com/api/storesearch/"
STEAM_APP_DETAILS = "https://store.steampowered.com/api/appdetails"

SteamConfidence = Literal["high", "medium", "low"]

_log = logging.getLogger(__name__)


class SteamLookupResult:
    __slots__ = ("app_id", "name", "header_image", "price_final_usd", "currency", "confidence", "detail_note")

    def __init__(
        self,
        *,
        app_id: int,
        name: str,
        header_image: str | None,
        price_final_usd: float | None,
        currency: str,
        confidence: SteamConfidence,
        detail_note: str | None = None,
    ) -> None:
        self.app_id = app_id
        self.name = name
        self.header_image = header_image
        self.price_final_usd = price_final_usd
        self.currency = currency
        self.confidence = confidence
        self.detail_note = detail_note


def _alnum_tokens(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else " " for ch in value)
    return " ".join(cleaned.split())


async def steam_store_search(*, term: str, timeout: float = 25.0) -> list[dict[str, Any]]:
    q = term.strip()
    if not q:
        return []
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            STEAM_STORE_SEARCH,
            params={"term": q, "cc": "US", "l": "en"},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    return [row for row in items if isinstance(row, dict)]


async def steam_app_details(*, app_id: int, timeout: float = 25.0) -> dict[str, Any] | None:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            STEAM_APP_DETAILS,
            params={"appids": str(app_id), "cc": "US", "l": "en"},
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        outer = response.json()
    bucket = outer.get(str(app_id)) if isinstance(outer, dict) else None
    if not isinstance(bucket, dict) or not bucket.get("success"):
        return None
    data = bucket.get("data")
    return data if isinstance(data, dict) else None


def _steam_final_price_usd(data: dict[str, Any]) -> tuple[float | None, str]:
    overview = data.get("price_overview")
    if not isinstance(overview, dict):
        return None, "USD"
    currency = str(overview.get("currency") or "USD")
    final = overview.get("final")
    try:
        cents = int(final)
    except (TypeError, ValueError):
        return None, currency
    if currency != "USD":
        # Steam returns localized overview — treat non-USD as informational only for numeric USD slot.
        try:
            return float(cents) / 100.0, currency
        except Exception:
            return None, currency
    return float(cents) / 100.0, currency


def _pick_search_hit(items: list[dict[str, Any]], title: str) -> tuple[dict[str, Any] | None, SteamConfidence]:
    if not items:
        return None, "low"
    target = _alnum_tokens(title)
    best_exact: dict[str, Any] | None = None
    best_partial: dict[str, Any] | None = None
    for row in items:
        name = row.get("name")
        if not isinstance(name, str):
            continue
        cand_tokens = _alnum_tokens(name)
        if cand_tokens == target and cand_tokens:
            best_exact = row
            break
        if target and target in cand_tokens and len(target) >= 4:
            best_partial = row
    chosen = best_exact or best_partial or items[0]
    conf: SteamConfidence = "high" if best_exact else ("medium" if best_partial else "low")
    return chosen, conf


async def resolve_steam_lookup(game: GameSummary) -> SteamLookupResult | None:
    """Resolve Steam listing via IGDB-linked app id or Store Search fallback."""
    try:
        header_image: str | None = None
        price_usd: float | None = None
        currency = "USD"
        detail_note: str | None = None

        data: dict[str, Any] | None = None
        resolved_name = game.title
        confidence: SteamConfidence = "low"
        app_id: int | None = None

        if game.steam_app_id is not None:
            app_id = int(game.steam_app_id)
            data = await steam_app_details(app_id=app_id)
            confidence = "high"
            if data:
                resolved_name = str(data.get("name") or game.title)
                header_image = data.get("header_image") if isinstance(data.get("header_image"), str) else None
                price_usd, currency = _steam_final_price_usd(data)
        else:
            hits = await steam_store_search(term=game.title)
            picked, hit_conf = _pick_search_hit(hits, game.title)
            if not picked:
                return None
            raw_id = picked.get("id") or picked.get("appid")
            try:
                app_id = int(raw_id)
            except (TypeError, ValueError):
                return None
            confidence = hit_conf
            resolved_name = str(picked.get("name") or game.title)
            data = await steam_app_details(app_id=app_id)
            if data:
                resolved_name = str(data.get("name") or resolved_name)
                header_image = data.get("header_image") if isinstance(data.get("header_image"), str) else None
                price_usd, currency = _steam_final_price_usd(data)

        if app_id is None:
            return None

        if confidence == "low":
            detail_note = "Low-confidence Steam catalog match — verify this is the edition you mean."

        return SteamLookupResult(
            app_id=app_id,
            name=resolved_name,
            header_image=header_image,
            price_final_usd=price_usd,
            currency=currency,
            confidence=confidence,
            detail_note=detail_note,
        )
    except Exception as exc:  # noqa: BLE001 — treat outage like “no Steam match”
        _log.warning("Steam lookup failed for %r: %s", game.title, exc)
        return None


def apply_steam_cover_fallback(game: GameSummary, steam: SteamLookupResult | None) -> GameSummary:
    if not steam or not steam.header_image:
        return game
    if game.cover_image_url:
        return game
    allow_overlay = steam.confidence in {"high", "medium"}
    if not allow_overlay:
        return game
    merged_sources = [*game.cover_sources, "steam:header"]
    return game.model_copy(update={"cover_image_url": steam.header_image, "cover_sources": merged_sources})


def steam_storefront_url(app_id: int) -> str:
    return f"https://store.steampowered.com/app/{app_id}/"
