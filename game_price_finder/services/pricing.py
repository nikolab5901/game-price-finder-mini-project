from __future__ import annotations

import logging
import statistics
from typing import Any
from urllib.parse import quote_plus

from game_price_finder.models import GamePricingPage, GameSummary, PriceEstimate, PriceHistoryChart, SoldBand, SourceOffer, utcnow
from game_price_finder.services.cheapshark import CheapSharkPrefetch, deal_price_usd, fetch_cheapshark_snapshot, store_id_to_name
from game_price_finder.services.research_links import marketplace_query_for_game, research_listing_offers
from game_price_finder.services.steam import SteamLookupResult, steam_storefront_url

_log = logging.getLogger(__name__)


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    return float(statistics.median(vals))


def _percentiles(vals: list[float]) -> tuple[float | None, float | None, float | None]:
    if len(vals) < 4:
        med = _median(vals)
        return med, med, med
    xs = sorted(vals)

    def pct(p: float) -> float:
        k = (len(xs) - 1) * p
        f = int(k)
        c = min(f + 1, len(xs) - 1)
        if f == c:
            return float(xs[f])
        return float(xs[f] + (xs[c] - xs[f]) * (k - f))

    return pct(0.25), pct(0.5), pct(0.75)


def _parse_item_price_usd(row: dict[str, Any]) -> float | None:
    price = row.get("price")
    if not isinstance(price, dict):
        return None
    value = price.get("value")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bucket_for_condition(condition_id: Any) -> str | None:
    if not condition_id:
        return None
    cid = str(condition_id).upper()
    if cid in {"NEW", "OPEN_BOX"}:
        return "new"
    if cid.startswith("USED") or cid in {"FOR_PARTS_OR_NOT_WORKING", "REFURBISHED", "LIKE_NEW"}:
        return "used"
    return None


def ebay_market_section(
    game: GameSummary,
    summaries: list[dict[str, Any]],
    *,
    ebay_skip_reason: str | None = None,
    window_days: int = 14,
) -> tuple[list[PriceEstimate], SoldBand | None, SourceOffer | None, list[str]]:
    now = utcnow()
    notes: list[str] = []

    if ebay_skip_reason:
        notes.append(ebay_skip_reason)
        return [], None, None, notes

    if not summaries:
        notes.append(
            "No active eBay listings matched this catalog-derived query — widen keywords or retry later.",
        )
        return [], None, None, notes

    new_prices: list[float] = []
    used_prices: list[float] = []

    for row in summaries:
        amount = _parse_item_price_usd(row)
        if amount is None:
            continue
        bucket = _bucket_for_condition(row.get("conditionId"))
        if bucket == "new":
            new_prices.append(amount)
        elif bucket == "used":
            used_prices.append(amount)
        else:
            used_prices.append(amount)

    estimates: list[PriceEstimate] = []
    if new_prices:
        lo, med, hi = _percentiles(new_prices)
        estimates.append(
            PriceEstimate(
                channel="new",
                basis="ask",
                currency="USD",
                window_days=window_days,
                sample_size=len(new_prices),
                value_usd=med,
                low_usd=lo,
                high_usd=hi,
                as_of=now,
            )
        )
    if used_prices:
        lo, med, hi = _percentiles(used_prices)
        estimates.append(
            PriceEstimate(
                channel="used",
                basis="ask",
                currency="USD",
                window_days=window_days,
                sample_size=len(used_prices),
                value_usd=med,
                low_usd=lo,
                high_usd=hi,
                as_of=now,
            )
        )

    sold_prices_sample = used_prices or new_prices
    sold_band: SoldBand | None = None
    if sold_prices_sample:
        p25, med, p75 = _percentiles(sold_prices_sample)
        sold_band = SoldBand(
            currency="USD",
            window_days=window_days,
            sample_size=len(sold_prices_sample),
            p25_usd=p25,
            median_usd=med,
            p75_usd=p75,
            basis="ask",
            note="Derived from active listings (not verified sold comps).",
        )
        notes.append(
            "The sale-style band uses current asking prices until a dedicated sold-comps feed is connected.",
        )

    notes.append("eBay Browse API surfaces asks — realized resale can differ after fees/shipping.")

    row = SourceOffer(
        source="eBay",
        label=f"Active listings snapshot ({len(summaries)} items scanned)",
        url=f"https://www.ebay.com/sch/i.html?_nkw={quote_plus(marketplace_query_for_game(game))}",
        price_low_usd=min(new_prices or used_prices) if (new_prices or used_prices) else None,
        price_high_usd=max(new_prices or used_prices) if (new_prices or used_prices) else None,
        condition="Mixed",
        fetched_at=now,
    )

    return estimates, sold_band, row, notes


def _cheapshark_buyer_signal_notes(deals: list[dict[str, Any]]) -> list[str]:
    notes: list[str] = []
    meta_vals: list[int] = []
    steam_snippets: list[str] = []
    savings_vals: list[float] = []

    for deal in deals[:12]:
        ms = deal.get("metacriticScore")
        if ms not in (None, "", "0", 0):
            try:
                v = int(float(str(ms).strip()))
                if v > 0:
                    meta_vals.append(v)
            except (TypeError, ValueError):
                pass

        st = deal.get("steamRatingText")
        pct = deal.get("steamRatingPercent")
        if isinstance(st, str) and st.strip():
            label = st.strip()
            if isinstance(pct, str) and pct.strip():
                snippet = f"{label} ({pct.strip()}% positive on sampled Steam-facing rows)"
            elif pct not in (None, ""):
                snippet = f"{label} ({pct}% positive on sampled Steam-facing rows)"
            else:
                snippet = label
            if snippet not in steam_snippets:
                steam_snippets.append(snippet)

        sv = deal.get("savings")
        if sv not in (None, "", "0", 0):
            try:
                savings_vals.append(float(str(sv).strip()))
            except (TypeError, ValueError):
                pass

    if meta_vals:
        notes.append(
            f"CheapShark rows include publisher Metacritic hints up to {max(meta_vals)}/100 — scores attach to specific storefront SKUs, not every resale scenario.",
        )
    if steam_snippets:
        notes.append(f"Steam review summaries echoed on sampled deals: {steam_snippets[0]} — sentiment only, not resale guidance.")
    if savings_vals:
        med_sv = sorted(savings_vals)[len(savings_vals) // 2]
        notes.append(
            f"Median advertised discount depth on sampled deals ≈ {med_sv:.0f}% off list — promotions expire quickly; verify current carts.",
        )
    return notes


def steam_market_section(steam: SteamLookupResult | None) -> tuple[list[SourceOffer], list[PriceEstimate], list[str]]:
    now = utcnow()
    if steam is None:
        return [], [], []

    notes: list[str] = []
    if steam.detail_note:
        notes.append(steam.detail_note)

    conf_label = {"high": "IGDB-linked", "medium": "Title match", "low": "Tentative"}[steam.confidence]
    currency_suffix = "" if steam.currency == "USD" else f" ({steam.currency})"

    label_parts = [f"Steam catalog ({conf_label})", steam.name]
    offer = SourceOffer(
        source="Steam",
        label=" · ".join(label_parts) + currency_suffix,
        url=steam_storefront_url(steam.app_id),
        price_usd=steam.price_final_usd if steam.currency == "USD" else None,
        fetched_at=now,
        condition="Digital license",
    )

    estimates: list[PriceEstimate] = []
    if steam.price_final_usd is not None and steam.currency == "USD":
        estimates.append(
            PriceEstimate(
                channel="unknown",
                basis="ask",
                currency="USD",
                window_days=1,
                sample_size=1,
                value_usd=steam.price_final_usd,
                low_usd=steam.price_final_usd,
                high_usd=steam.price_final_usd,
                as_of=now,
                disclaimer="Steam storefront snapshot — excludes regional tax/VAT and bundle quirks.",
            )
        )
    elif steam.price_final_usd is not None:
        notes.append(
            f"Steam returned pricing in {steam.currency}; listing appears on the Steam row without USD normalization.",
        )

    return [offer], estimates, notes


async def cheapshark_market_section(
    game: GameSummary,
    *,
    prefetch: CheapSharkPrefetch | None = None,
) -> tuple[list[SourceOffer], list[PriceEstimate], list[str]]:
    now = utcnow()
    notes: list[str] = [
        "CheapShark aggregates promotions from authorized PC storefront partners — skew digital.",
    ]
    deals, picked, _bundle_unused = prefetch if prefetch is not None else await fetch_cheapshark_snapshot(game)
    if not picked:
        notes.append("CheapShark found no catalog row close to this IGDB title.")
        return [], [], notes

    notes.extend(_cheapshark_buyer_signal_notes(deals))

    try:
        stores = await store_id_to_name()
    except Exception as exc:  # noqa: BLE001 — keep deals with Store N fallback labels
        _log.warning("CheapShark store name map unavailable: %s", exc)
        stores = {}
    sources: list[SourceOffer] = []
    prices: list[float] = []

    for deal in deals[:8]:
        price = deal_price_usd(deal)
        if price is None:
            continue
        prices.append(price)
        sid_raw = deal.get("storeID")
        try:
            sid = int(sid_raw)
        except (TypeError, ValueError):
            sid = -1
        store_name = stores.get(sid, f"Store {sid}")
        title = deal.get("title")
        label = str(title) if title else "Digital deal"
        extras: list[str] = []
        np = deal.get("normalPrice")
        if np not in (None, "", "0"):
            try:
                npf = float(str(np).strip())
                extras.append(f"MSRP ${npf:.2f}")
            except (TypeError, ValueError):
                pass
        ms = deal.get("metacriticScore")
        if ms not in (None, "", "0", 0):
            try:
                mv = int(float(str(ms).strip()))
                if mv > 0:
                    extras.append(f"Metacritic {mv}")
            except (TypeError, ValueError):
                pass
        if extras:
            label = f"{label[:110]} ({' · '.join(extras)})"

        url = deal.get("dealURL")
        url_str = str(url) if isinstance(url, str) else None
        sources.append(
            SourceOffer(
                source=f"CheapShark · {store_name}",
                label=label[:160],
                url=url_str,
                price_usd=price,
                fetched_at=now,
                condition="Digital promo",
            )
        )

    estimates: list[PriceEstimate] = []
    if prices:
        lo, med, hi = _percentiles(prices)
        estimates.append(
            PriceEstimate(
                channel="unknown",
                basis="ask",
                currency="USD",
                window_days=7,
                sample_size=len(prices),
                value_usd=med,
                low_usd=lo,
                high_usd=hi,
                as_of=now,
                disclaimer="Median of scanned CheapShark promos — availability changes frequently.",
            )
        )

    return sources, estimates, notes


def assemble_game_page(
    game: GameSummary,
    *,
    ebay_summaries: list[dict[str, Any]],
    ebay_skip_reason: str | None = None,
    steam: SteamLookupResult | None,
    cheapshark_sources: list[SourceOffer],
    cheapshark_estimates: list[PriceEstimate],
    cheapshark_notes: list[str],
    price_history_chart: PriceHistoryChart | None = None,
) -> GamePricingPage:
    methodology: list[str] = [
        "How to read this board: physical resale asks (eBay) behave differently from Steam licenses or CheapShark-tracked PC sales.",
        "Treat each column as its own signal — mixing them without context will distort buy/sell decisions.",
    ]

    ebay_estimates, sold_band, ebay_snapshot_row, ebay_notes = ebay_market_section(
        game,
        ebay_summaries,
        ebay_skip_reason=ebay_skip_reason,
    )
    methodology.extend(ebay_notes)

    steam_sources, steam_estimates, steam_notes = steam_market_section(steam)
    methodology.extend(steam_notes)
    methodology.extend(cheapshark_notes)

    estimates = [*ebay_estimates, *steam_estimates, *cheapshark_estimates]

    sources: list[SourceOffer] = []
    if ebay_snapshot_row:
        sources.append(ebay_snapshot_row)
    sources.extend(research_listing_offers(game, include_active_hub=ebay_snapshot_row is None))
    sources.extend(steam_sources)
    sources.extend(cheapshark_sources)
    sources.extend(_placeholder_retail_searches(game))

    return GamePricingPage(
        game=game,
        estimates=estimates,
        sources=sources,
        sold_band=sold_band,
        methodology_notes=methodology,
        price_history_chart=price_history_chart,
    )


def enrich_fixture_page(page: GamePricingPage, *, enriched_game: GameSummary) -> GamePricingPage:
    """Preserve fixture economics while swapping in richer imagery/metadata."""
    return page.model_copy(update={"game": enriched_game})


def build_pricing_from_ebay(
    *,
    game: GameSummary,
    summaries: list[dict[str, Any]],
    window_days: int = 14,
) -> GamePricingPage:
    """Backward-compatible helper — delegates to assembler without CheapShark/Steam extras."""
    _ = window_days
    return assemble_game_page(
        game,
        ebay_summaries=summaries,
        ebay_skip_reason=None,
        steam=None,
        cheapshark_sources=[],
        cheapshark_estimates=[],
        cheapshark_notes=[],
    )


def _placeholder_retail_searches(game: GameSummary) -> list[SourceOffer]:
    q = quote_plus(game.title)
    now = utcnow()
    return [
        SourceOffer(
            source="GameStop",
            label="Search pre-owned inventory (no public API)",
            url=f"https://www.gamestop.com/search?q={q}",
            fetched_at=now,
        ),
        SourceOffer(
            source="Amazon",
            label="Third-party seller marketplace snapshot",
            url=f"https://www.amazon.com/s?k={q}",
            fetched_at=now,
        ),
        SourceOffer(
            source="PriceCharting",
            label="Historical cartridge/disc comps (external)",
            url=f"https://www.pricecharting.com/search-products?q={q}",
            fetched_at=now,
        ),
    ]
