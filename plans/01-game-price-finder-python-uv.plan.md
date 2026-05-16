---
name: Game Price Finder Web
cursor_source_slug: game_price_finder_web_96bdd9fe
overview: "Scaffold a browser-based web app in Python (FastAPI) managed with UV: simple accessible UI via server-rendered templates (optional HTMX), search games, show estimated new/used averages, per-source rows, and recent-sold bands from marketplace APIs where keys exist, with demo fixtures when unavailable."
todos:
  - id: scaffold-uv-fastapi
    content: Initialize project with UV (`pyproject.toml`, lockfile, `.python-version`), FastAPI app layout, dev command (`uv run uvicorn`), static/templates dirs, base Jinja layout and styling approach.
    status: pending
  - id: pydantic-dtos
    content: Define Pydantic models (GameSummary, PriceEstimate, SourceOffer) and route/query schemas; validate outbound JSON and IGDB/eBay adapter payloads where helpful.
    status: pending
  - id: igdb-search
    content: Implement IGDB OAuth + search/detail in Python service layer; wire FastAPI routes; fixture fallback + `USE_FIXTURES` env flag.
    status: pending
  - id: ebay-pricing
    content: Implement eBay OAuth/token + pricing fetch in services; map to internal models; fixture fallback when keys unavailable.
    status: pending
  - id: ui-flows
    content: Build Jinja templates for search → results → game detail (stat cards, sold band, sources table); optional HTMX for autocomplete; strong a11y/empty/error states.
    status: pending
  - id: docs-env
    content: Add `.env.example` + README for UV workflows, Python version, API keys, rate limits, MVP limitations (GameStop etc.).
    status: pending
repo_snapshot: plans/01-game-price-finder-python-uv.plan.md
---

# Game Price Finder (web, Python) — implementation plan

## Context

- Workspace **Game Price Finder Mini Project** was **empty** (greenfield at plan time).
- **Web** delivery and a **hybrid data approach**: **official/API-backed integrations** where practical, plus an **MVP path** using **fixtures and clear placeholders** when a source is blocked, rate-limited, or not yet integrated.
- **Stack**: **Python** with **UV** for pinning, resolution, venvs, and **`uv run`**.

## Product shape (what ships in v1)

- **Primary flow**: prominent **search bar** → **game detail** view.
- **Hero summary**: **median or trimmed-mean** for **new** and **used** (when distinguishable), labeled **estimate** with **data freshness**.
- **Breakdown**: scannable **list/table** of sources (eBay; placeholders for GameStop/others) with **price or range**, **condition**, **link out**.
- **Selling angle**: **recent sold comps** (or p25–p75 band) separate from **current ask** prices.
- **Accessibility & clarity**: large type, contrast, keyboard-friendly search, explicit loading/empty/error states.

## Recommended stack (Python + UV)

| Layer | Choice | Rationale |
|--------|--------|-----------|
| Tooling | **[UV](https://github.com/astral-sh/uv)** | Fast installs, reproducible **`uv.lock`**, **`uv sync`** / **`uv run`**. |
| Python | **3.12.x** (`.python-version`) | Stable baseline; 3.13 optional later. |
| Web framework | **[FastAPI](https://fastapi.tiangolo.com/)** | Async HTTP, OpenAPI, **Pydantic**. |
| HTTP client | **`httpx`** (async) | IGDB/eBay calls. |
| Settings | **`pydantic-settings`** | `.env`, secrets server-side. |
| Templates | **Jinja2** | Server-rendered HTML. |
| Progressive enhancement | **HTMX** (optional) | Partial updates without SPA. |
| CSS | Hand-written **or** Tailwind CLI later | Avoid Node in v1 if desired. |

## Architecture (data flow)

```mermaid
flowchart LR
  user[User_browser]
  templates[Jinja_templates]
  api[FastAPI_routes]
  services[Python_services]
  igdb[IGDB_API]
  ebay[eBay_APIs]
  fixtures[Local_fixtures_JSON]

  user --> templates
  user --> api
  templates --> api
  api --> services
  services --> igdb
  services --> ebay
  services --> fixtures
```

## Project layout (illustrative)

- `pyproject.toml`, `uv.lock`, `.python-version`
- `game_price_finder/` — `main.py`, `services/`, `models.py`, `templates/`, `static/`

## Data sources (v1)

| Need | Practical approach |
|------|--------------------|
| Game search + artwork | **IGDB** (Twitch client id/secret). |
| Marketplace pricing | **eBay** developer APIs (access varies). |
| Retail chains | No stable public API → **placeholders** or fixtures; avoid scraping without acceptance of risk. |

## Configuration

- **`.env`** + **`.env.example`**: Twitch/IGDB, eBay, **`USE_FIXTURES=true`**.

## Milestones

1. Scaffold UV + FastAPI + Jinja + CSS.
2. Routes/services for search + pricing views.
3. IGDB + fixtures.
4. eBay + fixtures.
5. UI polish; optional HTMX.
6. README for keys and limits.

## Out of scope for v1

Accounts, synced watchlists, fee calculators, alerts at scale, scraping catalogs, native apps.
