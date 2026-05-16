# Game Price Finder

**User guide:** [USAGE.md](USAGE.md) — how to run the app and use the UI.

Browser-friendly mini app that searches normalized game titles (via IGDB when Twitch credentials exist), blends **Steam Store** discovery (no personal API key), **CheapShark** PC storefront promotions (public JSON API at `/api/1.0`, requires a descriptive `User-Agent`), optional **eBay Browse** marketplace asks when developer keys exist, and ships curated fixtures for offline demos.

**`USE_FIXTURES`** controls whether authored demo rows from `demo_fixtures.json` load — it **does not** disable IGDB search when Twitch keys are present. Search routes hit IGDB whenever `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` are set (fixtures remain useful for deterministic layouts + seeded IDs). Without Twitch keys you only get substring matches against fixture titles.

Set `USE_FIXTURES=false` in `.env` once Twitch credentials exist if you prefer hiding demo banners while staying on IGDB-backed catalog search (eBay credentials remain optional).

## Prerequisites

- [UV](https://docs.astral.sh/uv/) (`uv --version`)
- CPython **3.12+** (UV will bootstrap `.venv/` automatically)

## Quick start (fixture mode)

```powershell
cd "c:\...\Game Price Finder Mini Project"
copy .env.example .env   # defaults USE_FIXTURES=true in the sample file
uv sync
uv run uvicorn game_price_finder.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 — search for **demo** or open demo IDs such as `/games/900001`.

## Project plans

Implementation plan snapshots: [`plans/01-game-price-finder-python-uv.plan.md`](plans/01-game-price-finder-python-uv.plan.md), [`plans/02-covers-apis-ui-polish.plan.md`](plans/02-covers-apis-ui-polish.plan.md), [`plans/03-search-franchise-fuzzy-prices.plan.md`](plans/03-search-franchise-fuzzy-prices.plan.md). Index and syncing notes: [`plans/README.md`](plans/README.md).

## Live integrations

| Provider | Credentials | Purpose |
|----------|-------------|---------|
| Twitch / IGDB | Free Twitch developer app (`TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`) | Catalog search, franchise coverage, upgraded cover URLs, Steam app linkage |
| Steam Store JSON | None | Header artwork fallback + USD storefront pricing when `cc=US` |
| CheapShark | None | Authorized PC storefront deal snapshots (`/api/1.0`) keyed off title / Steam app id |
| eBay Browse API | Optional (`EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`) | Active resale listings / asks |

Retail chains without stable partner APIs surface as outbound links only (GameStop, Amazon, PriceCharting, etc.).

### Important caveats

- **Browse API ≠ sold comps.** Live mode derives bands from **asking prices**. Labels call out when numbers are asks vs illustrative fixtures.
- **Steam + CheapShark skew toward PC/digital licenses.** Treat them separately from cartridge/disc resale economics on consoles.
- **Regional variance.** Defaults target `EBAY_US`; swap `EBAY_MARKETPLACE_ID` only after verifying token scopes cover other locales.
- **Rate limits.** Respect Twitch/eBay quotas; failures bubble back as UI warnings rather than opaque 500s where practical.

## Development commands

```powershell
uv sync                      # install deps from uv.lock
uv run uvicorn game_price_finder.main:app --reload
uv run python -m compileall game_price_finder
```

Health probe: `GET /healthz`. Debounced catalog dropdown (when Twitch keys exist): `GET /partials/search-suggestions?q=…`.

## Layout

- `game_price_finder/main.py` — FastAPI routes + static/template wiring  
- `game_price_finder/services/` — IGDB search/covers, Steam + CheapShark enrichment, eBay Browse, pricing assembly  
- `game_price_finder/fixture_catalog.py` — fixture loader (`demo_fixtures.json`)  
- `game_price_finder/templates/` — Jinja UI  
- `game_price_finder/static/styles.css` — accessible styling with automatic light/dark palettes  
