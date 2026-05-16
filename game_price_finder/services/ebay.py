from __future__ import annotations

import base64
from typing import Any

import httpx

from game_price_finder.config import Settings


def _api_roots(settings: Settings) -> tuple[str, str]:
    if settings.ebay_environment.strip().lower() == "sandbox":
        return (
            "https://api.sandbox.ebay.com",
            "https://api.sandbox.ebay.com/buy/browse/v1",
        )
    return (
        "https://api.ebay.com",
        "https://api.ebay.com/buy/browse/v1",
    )


async def fetch_ebay_application_token(settings: Settings) -> str:
    api_root, _ = _api_roots(settings)
    token_url = f"{api_root}/identity/v1/oauth2/token"
    raw = f"{settings.ebay_client_id}:{settings.ebay_client_secret}".encode()
    basic = base64.b64encode(raw).decode("ascii")
    scope = "https://api.ebay.com/oauth/api_scope"

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            token_url,
            headers={
                "Authorization": f"Basic {basic}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data={
                "grant_type": "client_credentials",
                "scope": scope,
            },
        )
        response.raise_for_status()
        data = response.json()
        return str(data["access_token"])


async def browse_search_summaries(
    *,
    settings: Settings,
    search_query: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if not settings.ebay_client_id or not settings.ebay_client_secret:
        return []

    _, browse_root = _api_roots(settings)
    token = await fetch_ebay_application_token(settings)

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{browse_root}/item_summary/search",
            headers={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": settings.ebay_marketplace_id,
            },
            params={
                "q": search_query,
                "limit": str(limit),
            },
        )
        response.raise_for_status()
        payload = response.json()

    summaries = payload.get("itemSummaries") if isinstance(payload, dict) else None
    if not isinstance(summaries, list):
        return []

    normalized: list[dict[str, Any]] = []
    for row in summaries:
        if isinstance(row, dict):
            normalized.append(row)
    return normalized
