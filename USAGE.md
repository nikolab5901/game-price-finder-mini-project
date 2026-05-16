# Game Price Finder — user guide

## Visitors vs developers

- **Visitors** use whatever URL you host (HTTPS). They search and open game pages in the browser only—**no downloads, no Twitch/eBay login.** Catalog breadth and pricing come from APIs your **server** calls using credentials **you** configured on the host (see [DEPLOY.md](DEPLOY.md)).
- **Developers** run the app on their machine with UV and a local `.env` (steps below).

Short manual for running the web UI locally or understanding behavior. Integrations and caveats: [README.md](README.md).

## What this app does

Game Price Finder is a small **browser-based** app backed by a Python server. You search for a video game title, browse catalog matches (from IGDB when the **host** configured Twitch credentials), and open a **detail page** that pulls together **asking-price style signals** from public APIs—Steam storefront data where applicable, CheapShark PC deals, and optionally eBay Browse listings when the operator added eBay credentials.

Numbers are **orientation only** (many sources reflect listings or promotional floors, not guaranteed resale comps). With **`USE_FIXTURES=true`** on the server you also get bundled fixture pages from **`demo_fixtures.json`** (synthetic demos) plus **`popular_catalog.json`** (~150 widely known titles with **public factual metadata** — title / year / platforms — and **illustrative** economics only). Offline IDs **`910001`–`910151`** are synthetic bundle keys, **not** real IGDB identifiers.

**Fixture thumbnails:** Cards on **`/search`** use each fixture row’s stored **`cover_image_url`** (live IGDB routes still upgrade covers separately). Regenerate **`popular_catalog.json`** from [**`scripts/popular_catalog_seed.csv`**](scripts/popular_catalog_seed.csv) after edits:

```powershell
uv run python scripts/generate_popular_catalog.py
uv run python scripts/generate_popular_catalog.py --enrich-steam-covers --steam-cover-confidence medium
```

With **`--enrich-steam-covers`**, the script calls Steam’s public Store Search/AppDetails APIs (rate-limit friendly delays + 429 backoff), then fills remaining blanks with **CheapShark game thumbnails** where available. Set **`RAWG_API_KEY`** (env or `--rawg-api-key`) for an optional third pass that queries RAWG search **`background_image`** values—helpful for console-heavy exclusives Steam/CheapShark omit. Optional CSV columns **`steam_app_id`** and **`cover_image_url`** force exact storefront IDs or artwork URLs per row.

The generator also merges **`scripts/cover_fallbacks_override.json`** (Steam storefront headers plus Lutris/IGDB-cover URLs refreshed by **`scripts/populate_cover_fallbacks_lutris.py`**). After a CSV regeneration that wipes artwork, rerun:

```powershell
uv run python scripts/populate_cover_fallbacks_lutris.py
uv run python scripts/patch_catalog_covers_from_fallbacks.py
```

Use **`scripts/generate_popular_catalog.py --fail-on-missing-covers`** to fail the build when any bundled row still lacks a thumbnail after those merges.

**Hosting:** To give casual users the full catalog without asking them to install anything, deploy the FastAPI app and set Twitch secrets on the platform—see [DEPLOY.md](DEPLOY.md).

## Prerequisites (local development only)

Visitors of a **deployed** site only need a browser.

Install [UV](https://docs.astral.sh/uv/) and use **Python 3.12+** (UV creates `.venv/` when you sync). Details: [README.md — Prerequisites](README.md#prerequisites).

## How to run locally

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
- **Guides (`/guides`)** — Short orientation for **buyers** and **sellers**: interpreting asks vs comps, editions, sold listings, fees—still verify everything on external sites.
- **Catalog vs fixtures**
  - If **`TWITCH_CLIENT_ID`** and **`TWITCH_CLIENT_SECRET`** are set in `.env`, search uses **IGDB** for broad franchise-style queries (fixtures do **not** disable this).
  - Without those keys, search falls back to **substring matches on the bundled fixture catalog** only (when `USE_FIXTURES=true`). The UI explains this when relevant.
- **Live suggestions** — While Twitch keys are configured, typing in the search box loads debounced suggestions from **`GET /partials/search-suggestions`** (HTMX).
- **Results (`/search?q=…`)** — Cards link to **`/games/{igdb_id}`**. Rows that map to Steam may show a **CheapShark “deal floor” hint** on the card before you open the detail page.
- **Detail (`/games/{id}`)** — If the ID exists in the fixture catalog, that authored page loads first (still enriched with live Steam/CheapShark where possible). Otherwise, with Twitch keys, the app loads the title from IGDB and assembles pricing sections as in README.
- **RAWG / Giant Bomb** — With optional keys in `.env`, extra titles appear on `/search` after IGDB/fixtures; cards link to **`/games/rawg/{id}`** or **`/games/giantbomb/{guid}`** when applicable.
- **Feedback** — **`/feedback`** records suggestions (pricing corrections, wrong links, ideas) into SQLite (`FEEDBACK_DB_PATH`). Operators review via **`/feedback/admin`** when **`FEEDBACK_ADMIN_TOKEN`** is set (`?token=` or `Authorization: Bearer`).
- **Demo / offline IDs** — Synthetic demos from `demo_fixtures.json`: e.g. `/games/900001`. Curated popular titles live under **`910001`+** from `popular_catalog.json` (regenerate via `uv run python scripts/generate_popular_catalog.py`). Try clearing the query on **`/search`** in fixture mode to browse many bundled titles, or search **`demo`** for the original demo rows only.

## Configuration at a glance

Copy **`.env.example`** to **`.env`** and set variables there. Important flags:

| Variable | Role |
|----------|------|
| `USE_FIXTURES` | Enables demo fixture catalog rows and banner copy |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | Required for IGDB-backed search and live catalog detail (set on server when deployed; see [DEPLOY.md](DEPLOY.md)) |
| `RAWG_API_KEY` / `GIANT_BOMB_API_KEY` | Optional free-tier keys — merged extra titles after IGDB/fixtures when set |
| `CATALOG_MERGE_MAX_RESULTS` / `IGDB_SEARCH_LIMIT` / `CATALOG_RAWG_LIMIT` / `CATALOG_GB_LIMIT` | Tune how many catalog rows IGDB + supplemental APIs contribute before slicing |
| `CATALOG_SUGGESTIONS_*` | Separate caps for **`GET /partials/search-suggestions`** (dropdown stays lighter than full search by default) |
| `FEEDBACK_DB_PATH` / `FEEDBACK_ADMIN_TOKEN` | Optional SQLite path + secret for reviewing `/feedback` submissions ([DEPLOY.md](DEPLOY.md)) |
| `EBAY_*` | Optional; improves marketplace listing aggregation |

Full provider table and behavioral notes: [README.md — Live integrations](README.md#live-integrations).
