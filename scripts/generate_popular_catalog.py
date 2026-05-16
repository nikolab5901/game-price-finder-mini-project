#!/usr/bin/env python3
"""Build game_price_finder/popular_catalog.json from scripts/popular_catalog_seed.csv.

Synthetic igdb_id values start at 910001 (offline fixtures only — never real IGDB IDs).

Run from repo root:
    uv run python scripts/generate_popular_catalog.py
    uv run python scripts/generate_popular_catalog.py --enrich-steam-covers

Optional CSV columns (headers): steam_app_id, cover_image_url — manual overrides per row.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CSV_PATH = ROOT / "scripts" / "popular_catalog_seed.csv"
OUT_PATH = ROOT / "game_price_finder" / "popular_catalog.json"

START_SYNTHETIC_ID = 910001

_FIXED_AS_OF = "2026-05-01T18:00:00Z"


@dataclass(frozen=True)
class SeedRow:
    title: str
    year: int
    platforms: str
    steam_app_id: int | None = None
    cover_image_url: str | None = None


def _digest(title: str) -> int:
    return int(hashlib.sha256(title.encode("utf-8")).hexdigest()[:12], 16)


def _spread(seed: str, lo: float, hi: float) -> float:
    span = hi - lo
    return round(lo + (_digest(seed) % 10_000) / 10_000 * span, 2)


def _ebay_search_url(title: str) -> str:
    q = title.replace(" ", "+")
    return f"https://www.ebay.com/sch/i.html?_nkw={q}"


def _pricecharting_url(title: str) -> str:
    q = title.replace(" ", "+")
    return f"https://www.pricecharting.com/search-products?q={q}"


def build_entry(
    *,
    igdb_id: int,
    title: str,
    release_year: int,
    platform_summary: str,
    steam_app_id: int | None = None,
    cover_image_url: str | None = None,
    cover_sources: list[str] | None = None,
) -> dict:
    key_new = f"{title}|new"
    key_used = f"{title}|used"
    new_mid = _spread(key_new, 39.99, 64.99)
    used_mid = _spread(key_used, 18.99, 49.99)
    low_used = round(used_mid * 0.82, 2)
    high_used = round(used_mid * 1.18, 2)

    game: dict = {
        "igdb_id": igdb_id,
        "title": title,
        "platform_summary": platform_summary,
        "cover_image_url": cover_image_url,
        "release_year": release_year,
    }
    if steam_app_id is not None:
        game["steam_app_id"] = steam_app_id
    if cover_sources:
        game["cover_sources"] = cover_sources

    return {
        "game": game,
        "estimates": [
            {
                "channel": "new",
                "basis": "sold",
                "currency": "USD",
                "window_days": 90,
                "sample_size": max(12, (_digest(key_new) % 120) + 1),
                "value_usd": new_mid,
                "low_usd": round(new_mid * 0.9, 2),
                "high_usd": round(new_mid * 1.12, 2),
                "as_of": _FIXED_AS_OF,
                "disclaimer": "Offline fixture — illustrative pricing only.",
            },
            {
                "channel": "used",
                "basis": "sold",
                "currency": "USD",
                "window_days": 90,
                "sample_size": max(20, (_digest(key_used) % 200) + 1),
                "value_usd": used_mid,
                "low_usd": low_used,
                "high_usd": high_used,
                "as_of": _FIXED_AS_OF,
                "disclaimer": "Offline fixture — illustrative pricing only.",
            },
        ],
        "sources": [
            {
                "source": "eBay",
                "label": "Search sold / active listings (manual hub)",
                "url": _ebay_search_url(title),
                "fetched_at": _FIXED_AS_OF,
            },
            {
                "source": "PriceCharting",
                "label": "Historical resale reference (external)",
                "url": _pricecharting_url(title),
                "fetched_at": _FIXED_AS_OF,
            },
        ],
        "sold_band": {
            "currency": "USD",
            "window_days": 90,
            "sample_size": max(20, (_digest(title + "|band") % 200) + 1),
            "p25_usd": low_used,
            "median_usd": used_mid,
            "p75_usd": high_used,
            "basis": "sold",
            "note": "Illustrative offline band — not sourced from live marketplace pulls.",
        },
        "methodology_notes": [
            "Curated catalog metadata (title / release year / platforms) reflects widely published facts.",
            "Synthetic igdb_id is for bundled offline pages only — use Twitch + IGDB for authoritative IDs.",
            "Numeric estimates are placeholders so the UI can be exercised without API keys.",
        ],
    }


def load_rows(csv_path: Path) -> list[SeedRow]:
    rows: list[SeedRow] = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit(f"CSV has no header: {csv_path}")
        fnames = {h.strip().lower() for h in reader.fieldnames}
        required = {"title", "year", "platforms"}
        missing = required - fnames
        if missing:
            raise SystemExit(f"CSV missing columns {missing}: {csv_path}")

        def pick(row: dict[str, str], key: str) -> str:
            for k, v in row.items():
                if k.strip().lower() == key:
                    return (v or "").strip()
            return ""

        for row in reader:
            title = pick(row, "title")
            year_s = pick(row, "year")
            platforms = pick(row, "platforms")
            if not title or not year_s:
                continue
            try:
                year = int(year_s)
            except ValueError:
                raise SystemExit(f"Bad year for {title!r}: {year_s!r}") from None

            steam_raw = pick(row, "steam_app_id")
            steam_app_id: int | None = None
            if steam_raw:
                try:
                    steam_app_id = int(steam_raw)
                except ValueError:
                    raise SystemExit(f"Bad steam_app_id for {title!r}: {steam_raw!r}") from None

            cover_url = pick(row, "cover_image_url") or None

            rows.append(
                SeedRow(
                    title=title,
                    year=year,
                    platforms=platforms or "Various",
                    steam_app_id=steam_app_id,
                    cover_image_url=cover_url,
                ),
            )
    return rows


async def _enrich_one(
    entry: dict,
    seed: SeedRow,
    *,
    allowed_confidences: frozenset[str],
    sem: asyncio.Semaphore,
    polite_delay_s: float,
) -> None:
    async with sem:
        game = entry["game"]
        if game.get("cover_image_url"):
            return

        from game_price_finder.models import GameSummary
        from game_price_finder.services.steam import resolve_steam_lookup

        summary = GameSummary(
            title=seed.title,
            platform_summary=game.get("platform_summary"),
            steam_app_id=seed.steam_app_id,
        )
        steam = None
        backoff = 1.2
        for attempt in range(8):
            try:
                steam = await resolve_steam_lookup(summary)
                break
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 429:
                    raise
                if attempt >= 7:
                    break
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.85, 45.0)
        if polite_delay_s > 0:
            await asyncio.sleep(polite_delay_s)

        if not steam or not steam.header_image:
            return
        if steam.confidence not in allowed_confidences:
            return

        game["cover_image_url"] = steam.header_image
        game["steam_app_id"] = steam.app_id
        existing = list(game.get("cover_sources") or [])
        merged = [*existing, "steam:header"]
        game["cover_sources"] = merged


async def enrich_entries_cheapshark_thumbs(
    entries: list[dict],
    seeds: list[SeedRow],
    *,
    concurrency: int,
    polite_delay_s: float,
) -> None:
    """Fill remaining blanks using CheapShark game search thumbnails (often Steam capsules)."""
    sem = asyncio.Semaphore(max(1, concurrency))

    async def one(entry: dict, seed: SeedRow) -> None:
        async with sem:
            game = entry["game"]
            if game.get("cover_image_url"):
                return

            from game_price_finder.models import GameSummary
            from game_price_finder.services.cheapshark import cheapshark_search_games, pick_cheapshark_game_row

            summary = GameSummary(title=seed.title)
            backoff = 0.8
            rows: list | None = None
            for attempt in range(6):
                try:
                    rows = await cheapshark_search_games(title=seed.title)
                    break
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 429:
                        raise
                    if attempt >= 5:
                        rows = []
                        break
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 1.85, 30.0)

            if not rows:
                if polite_delay_s > 0:
                    await asyncio.sleep(polite_delay_s)
                return

            picked = pick_cheapshark_game_row(rows, summary)
            if not isinstance(picked, dict):
                if polite_delay_s > 0:
                    await asyncio.sleep(polite_delay_s)
                return

            thumb = picked.get("thumb")
            if isinstance(thumb, str) and thumb.startswith("http"):
                game["cover_image_url"] = thumb
                sid_raw = picked.get("steamAppID")
                try:
                    if sid_raw is not None and game.get("steam_app_id") is None:
                        game["steam_app_id"] = int(sid_raw)
                except (TypeError, ValueError):
                    pass
                existing = list(game.get("cover_sources") or [])
                game["cover_sources"] = [*existing, "cheapshark:thumb"]

            if polite_delay_s > 0:
                await asyncio.sleep(polite_delay_s)

    await asyncio.gather(*[one(e, s) for e, s in zip(entries, seeds, strict=True)])


async def enrich_entries_rawg_background(
    entries: list[dict],
    seeds: list[SeedRow],
    *,
    api_key: str,
    concurrency: int,
    polite_delay_s: float,
) -> None:
    """Fill gaps using RAWG search first-hit background_image (optional API key)."""
    sem = asyncio.Semaphore(max(1, concurrency))
    base = "https://api.rawg.io/api/games"
    headers = {"User-Agent": "GamePriceFinder-catalog-script/0.1"}

    async def one(entry: dict, seed: SeedRow) -> None:
        async with sem:
            game = entry["game"]
            if game.get("cover_image_url"):
                return

            backoff = 0.9
            bg: str | None = None
            for attempt in range(5):
                try:
                    async with httpx.AsyncClient(timeout=25.0, headers=headers) as client:
                        response = await client.get(
                            base,
                            params={"search": seed.title, "page_size": 1, "key": api_key},
                        )
                        response.raise_for_status()
                        payload = response.json()
                    results = payload.get("results") if isinstance(payload, dict) else None
                    if isinstance(results, list) and results:
                        first = results[0]
                        if isinstance(first, dict):
                            raw = first.get("background_image")
                            if isinstance(raw, str) and raw.startswith("http"):
                                bg = raw
                    break
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 429:
                        raise
                    if attempt >= 4:
                        break
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, 35.0)

            if bg:
                game["cover_image_url"] = bg
                existing = list(game.get("cover_sources") or [])
                game["cover_sources"] = [*existing, "rawg:background"]

            if polite_delay_s > 0:
                await asyncio.sleep(polite_delay_s)

    await asyncio.gather(*[one(e, s) for e, s in zip(entries, seeds, strict=True)])


async def enrich_entries_steam(
    entries: list[dict],
    seeds: list[SeedRow],
    *,
    confidence_mode: str,
    concurrency: int,
    polite_delay_s: float,
) -> None:
    allowed = (
        frozenset({"high", "medium", "low"})
        if confidence_mode == "low"
        else frozenset({"high", "medium"})
        if confidence_mode == "medium"
        else frozenset({"high"})
    )
    sem = asyncio.Semaphore(max(1, concurrency))
    await asyncio.gather(
        *[
            _enrich_one(e, s, allowed_confidences=allowed, sem=sem, polite_delay_s=polite_delay_s)
            for e, s in zip(entries, seeds, strict=True)
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate popular_catalog.json from CSV seed.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=CSV_PATH,
        help="Path to seed CSV (default: scripts/popular_catalog_seed.csv)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=OUT_PATH,
        help="Output JSON path (default: game_price_finder/popular_catalog.json)",
    )
    parser.add_argument(
        "--start-id",
        type=int,
        default=START_SYNTHETIC_ID,
        help=f"First synthetic igdb_id (default: {START_SYNTHETIC_ID})",
    )
    parser.add_argument(
        "--enrich-steam-covers",
        action="store_true",
        help="Fetch Steam storefront header images via public Store API (requires network).",
    )
    parser.add_argument(
        "--steam-cover-confidence",
        choices=("high", "medium", "low"),
        default="high",
        help="Steam title-match tier: high (exact tokens), medium (+partial), low (+first search hit; highest mismatch risk).",
    )
    parser.add_argument(
        "--enrich-concurrency",
        type=int,
        default=3,
        help="Max concurrent Steam lookups when enriching (default: 3).",
    )
    parser.add_argument(
        "--enrich-delay",
        type=float,
        default=0.25,
        help="Seconds to sleep after each Steam lookup (politeness; default: 0.25).",
    )
    parser.add_argument(
        "--rawg-api-key",
        default=os.environ.get("RAWG_API_KEY", ""),
        help="RAWG API key for a final thumbnail pass on gaps (or set RAWG_API_KEY env).",
    )
    args = parser.parse_args()

    seed_rows = load_rows(args.csv)
    if not seed_rows:
        raise SystemExit(f"No rows loaded from {args.csv}")

    entries: list[dict] = []
    nid = args.start_id
    seen_titles: set[str] = set()
    for row in seed_rows:
        norm = row.title.casefold()
        if norm in seen_titles:
            raise SystemExit(f"Duplicate title in seed CSV: {row.title!r}")
        seen_titles.add(norm)

        cover_url = row.cover_image_url
        cover_sources = ["csv:manual"] if cover_url else None
        entries.append(
            build_entry(
                igdb_id=nid,
                title=row.title,
                release_year=row.year,
                platform_summary=row.platforms,
                steam_app_id=row.steam_app_id,
                cover_image_url=cover_url,
                cover_sources=cover_sources,
            ),
        )
        nid += 1

    if args.enrich_steam_covers:

        async def _enrich_pipeline() -> None:
            await enrich_entries_steam(
                entries,
                seed_rows,
                confidence_mode=args.steam_cover_confidence,
                concurrency=args.enrich_concurrency,
                polite_delay_s=max(0.0, args.enrich_delay),
            )
            await enrich_entries_cheapshark_thumbs(
                entries,
                seed_rows,
                concurrency=max(1, args.enrich_concurrency),
                polite_delay_s=max(0.0, args.enrich_delay),
            )
            rawg_key = (args.rawg_api_key or "").strip()
            if rawg_key:
                await enrich_entries_rawg_background(
                    entries,
                    seed_rows,
                    api_key=rawg_key,
                    concurrency=max(1, args.enrich_concurrency),
                    polite_delay_s=max(0.0, args.enrich_delay),
                )

        asyncio.run(_enrich_pipeline())

    covered = sum(1 for e in entries if e["game"].get("cover_image_url"))
    payload = {"entries": entries}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} entries to {args.out} (ids {args.start_id}–{nid - 1})")
    print(f"Entries with cover_image_url: {covered}/{len(entries)}")


if __name__ == "__main__":
    main()
