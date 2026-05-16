"""Outbound research URLs for marketplace orientation (no transactions)."""

from __future__ import annotations

from urllib.parse import quote_plus

from game_price_finder.models import GameSummary, SourceOffer, utcnow


def marketplace_query_for_game(game: GameSummary) -> str:
    parts = [game.title]
    if game.platform_summary:
        parts.append(game.platform_summary.split(",", maxsplit=1)[0].strip())
    return " ".join(p for p in parts if p).strip()


def ebay_active_listings_url(game: GameSummary) -> str:
    q = quote_plus(marketplace_query_for_game(game))
    return f"https://www.ebay.com/sch/i.html?_nkw={q}"


def ebay_sold_listings_url(game: GameSummary) -> str:
    q = quote_plus(marketplace_query_for_game(game))
    return f"https://www.ebay.com/sch/i.html?_nkw={q}&LH_Complete=1&LH_Sold=1"


def steamdb_app_url(app_id: int) -> str:
    return f"https://steamdb.info/app/{int(app_id)}/"


def research_listing_offers(
    game: GameSummary,
    *,
    include_active_hub: bool,
) -> list[SourceOffer]:
    """Manual hubs distinct from Browse API snapshots — sold comps + optional active duplicate."""
    now = utcnow()
    offers: list[SourceOffer] = []
    if include_active_hub:
        offers.append(
            SourceOffer(
                source="eBay",
                label="Active listings hub (marketplace search)",
                url=ebay_active_listings_url(game),
                fetched_at=now,
            ),
        )
    offers.append(
        SourceOffer(
            source="eBay",
            label="Sold / completed listings hub (comps orientation)",
            url=ebay_sold_listings_url(game),
            fetched_at=now,
        ),
    )
    if game.steam_app_id is not None:
        offers.append(
            SourceOffer(
                source="SteamDB",
                label="Edition / bundle / depot reference (Steam app)",
                url=steamdb_app_url(game.steam_app_id),
                fetched_at=now,
            ),
        )
    return offers
