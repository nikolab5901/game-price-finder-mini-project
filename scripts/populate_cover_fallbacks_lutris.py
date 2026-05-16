#!/usr/bin/env python3
"""Populate scripts/cover_fallbacks_override.json using Lutris public search API."""

from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "game_price_finder" / "popular_catalog.json"
OUT_PATH = ROOT / "scripts" / "cover_fallbacks_override.json"

UA = {"User-Agent": "GamePriceFinder-catalog/0.1 (offline cover curator; Lutris JSON API)"}


def lutris_cover_for_title(client: httpx.Client, title: str) -> str | None:
    r = client.get(
        "https://lutris.net/api/games",
        params={"search": title},
        headers=UA,
        timeout=35.0,
    )
    if r.status_code != 200:
        return None
    payload = r.json()
    rows = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return None
    want = title.casefold().strip()
    chosen: dict | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("name")
        if isinstance(name, str) and name.casefold().strip() == want:
            chosen = row
            break
    if chosen is None and rows:
        first = rows[0]
        if isinstance(first, dict):
            chosen = first
    if chosen is None:
        return None
    cover = chosen.get("coverart")
    if isinstance(cover, str) and cover.startswith("http"):
        return cover
    return None


def main() -> None:
    cat = json.loads(CATALOG.read_text(encoding="utf-8"))
    entries = cat.get("entries") or []

    blob: dict = {}
    if OUT_PATH.is_file():
        blob = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    raw = blob.get("by_igdb_id") or {}
    by_id: dict[str, str] = {str(k): v for k, v in raw.items() if isinstance(v, str)}

    misses: list[tuple[str, str]] = []
    for e in entries:
        g = e["game"]
        if g.get("cover_image_url"):
            continue
        misses.append((str(int(g["igdb_id"])), str(g["title"])))

    with httpx.Client() as client:
        for sk, title in misses:
            if by_id.get(sk, "").startswith("http"):
                continue
            try:
                cover = lutris_cover_for_title(client, title)
            except httpx.HTTPError:
                cover = None
            if cover:
                by_id[sk] = cover
                print("OK", sk, title.split()[0][:12])
            else:
                print("--", sk, title[:60])
            time.sleep(0.45)

    blob["by_igdb_id"] = dict(sorted(by_id.items(), key=lambda kv: int(kv[0])))
    blob["_comment"] = "Mixed Steam storefront headers + Lutris-provided IGDB cover art lookups."
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(blob, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
