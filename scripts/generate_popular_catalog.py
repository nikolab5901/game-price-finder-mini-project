#!/usr/bin/env python3
"""Build game_price_finder/popular_catalog.json from scripts/popular_catalog_seed.csv.

Synthetic igdb_id values start at 910001 (offline fixtures only — never real IGDB IDs).

Run from repo root:
    uv run python scripts/generate_popular_catalog.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "scripts" / "popular_catalog_seed.csv"
OUT_PATH = ROOT / "game_price_finder" / "popular_catalog.json"

START_SYNTHETIC_ID = 910001

_FIXED_AS_OF = "2026-05-01T18:00:00Z"


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


def build_entry(*, igdb_id: int, title: str, release_year: int, platform_summary: str) -> dict:
    key_new = f"{title}|new"
    key_used = f"{title}|used"
    new_mid = _spread(key_new, 39.99, 64.99)
    used_mid = _spread(key_used, 18.99, 49.99)
    low_used = round(used_mid * 0.82, 2)
    high_used = round(used_mid * 1.18, 2)

    return {
        "game": {
            "igdb_id": igdb_id,
            "title": title,
            "platform_summary": platform_summary,
            "cover_image_url": None,
            "release_year": release_year,
        },
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


def load_rows(csv_path: Path) -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise SystemExit(f"CSV has no header: {csv_path}")
        expected = {"title", "year", "platforms"}
        missing = expected - {h.strip().lower() for h in reader.fieldnames}
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
            rows.append((title, year, platforms or "Various"))
    return rows


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
    args = parser.parse_args()

    seed_rows = load_rows(args.csv)
    if not seed_rows:
        raise SystemExit(f"No rows loaded from {args.csv}")

    entries = []
    nid = args.start_id
    seen_titles: set[str] = set()
    for title, year, platforms in seed_rows:
        norm = title.casefold()
        if norm in seen_titles:
            raise SystemExit(f"Duplicate title in seed CSV: {title!r}")
        seen_titles.add(norm)
        entries.append(build_entry(igdb_id=nid, title=title, release_year=year, platform_summary=platforms))
        nid += 1

    payload = {"entries": entries}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(entries)} entries to {args.out} (ids {args.start_id}–{nid - 1})")


if __name__ == "__main__":
    main()
