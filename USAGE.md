# Game Price Finder — user guide

Short manual for running the app and using the web UI. For developer setup, integrations, and caveats, see [README.md](README.md).

## What this app does

Game Price Finder is a small browser-based tool you run locally. You search for a video game title, browse normalized catalog matches (from IGDB when configured), and open a **detail page** that pulls together **asking-price style signals** from public APIs—Steam storefront data where applicable, CheapShark PC deals, and optionally eBay Browse listings when you add eBay credentials.

Numbers are **orientation only** (many sources reflect listings or promotional floors, not guaranteed resale comps). With **`USE_FIXTURES=true`** you also get curated **demo rows** from `demo_fixtures.json` for predictable layouts and stable IDs while offline or without Twitch keys.

## Prerequisites

Install [UV](https://docs.astral.sh/uv/) and use **Python 3.12+** (UV creates `.venv/` when you sync). Details: [README.md — Prerequisites](README.md#prerequisites).

## How to run

From the project root:

```powershell
cd "path\to\Game Price Finder Mini Project"
copy .env.example .env
uv sync
uv run uvicorn game_price_finder.main:app --reload --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** in your browser.

To confirm the server is up without the UI: **GET** http://127.0.0.1:8000/healthz

## How to use the UI

- **Home (`/`)** — Enter a title and submit to run a full search, or use **Search** in the header for the results page directly.
- **Catalog vs fixtures**
  - If **`TWITCH_CLIENT_ID`** and **`TWITCH_CLIENT_SECRET`** are set in `.env`, search uses **IGDB** for broad franchise-style queries (fixtures do **not** disable this).
  - Without those keys, search falls back to **substring matches on demo fixtures** only (when `USE_FIXTURES=true`). The UI explains this when relevant.
- **Live suggestions** — While Twitch keys are configured, typing in the search box loads debounced suggestions from **`GET /partials/search-suggestions`** (HTMX).
- **Results (`/search?q=…`)** — Cards link to **`/games/{igdb_id}`**. Rows that map to Steam may show a **CheapShark “deal floor” hint** on the card before you open the detail page.
- **Detail (`/games/{id}`)** — If the ID exists in the fixture catalog, that authored page loads first (still enriched with live Steam/CheapShark where possible). Otherwise, with Twitch keys, the app loads the title from IGDB and assembles pricing sections as in README.
- **Demo IDs** — Example fixture URLs (IDs depend on `demo_fixtures.json`): e.g. `/games/900001`, `/games/900002`. Try searching **`demo`** in fixture mode to list sample titles.

## Configuration at a glance

Copy **`.env.example`** to **`.env`** and set variables there. Important flags:

| Variable | Role |
|----------|------|
| `USE_FIXTURES` | Enables demo fixture catalog rows and banner copy |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | Required for IGDB-backed search and live catalog detail |
| `EBAY_*` | Optional; improves marketplace listing aggregation |

Full provider table and behavioral notes: [README.md — Live integrations](README.md#live-integrations).
