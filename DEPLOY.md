# Deploying Game Price Finder (zero friction for visitors)

This app is **server-rendered FastAPI**. Visitors only need a browser and your **HTTPS URL**. They **do not** install UV/Python, edit `.env`, or sign in to Twitch or eBay.

**Who configures API keys:** You (the operator) register **developer applications** with Twitch (for IGDB) and optionally eBay, then paste **application** credentials into your hosting provider’s **secret environment variables**. Those secrets stay on the server and never ship to visitors’ browsers.

## Visitors vs developers

| Audience | What they do |
|----------|----------------|
| **Visitors** | Open your deployed site, search, open game detail pages. No accounts, no downloads. |
| **Developers** | Clone the repo, run `uv sync` / `uvicorn` locally, use `.env` for secrets. See [README.md](README.md) and [USAGE.md](USAGE.md). |

## Required and optional environment variables

Set these in your host’s dashboard (Render, Railway, Fly.io, Azure, etc.). Names match [.env.example](.env.example).

| Variable | Required for public catalog? | Purpose |
|----------|------------------------------|---------|
| `TWITCH_CLIENT_ID` | **Yes**, for IGDB-backed search/detail | Twitch developer app Client ID |
| `TWITCH_CLIENT_SECRET` | **Yes**, same | Twitch developer app Client Secret (confidential — server only) |
| `USE_FIXTURES` | No | `true` shows demo banners + fixture IDs; `false` is typical for a public “live catalog” demo |
| `EBAY_CLIENT_ID` | No | Optional Browse API listings |
| `EBAY_CLIENT_SECRET` | No | Optional Browse API |
| `EBAY_ENVIRONMENT` | No | `production` or `sandbox` (default `production`) |
| `EBAY_MARKETPLACE_ID` | No | Default `EBAY_US` |
| `RAWG_API_KEY` | No | Merge supplemental RAWG catalog rows ([RAWG API](https://rawg.io/apidocs)) |
| `GIANT_BOMB_API_KEY` | No | Merge supplementary Giant Bomb rows (respect daily limits) |
| `FEEDBACK_DB_PATH` | No | SQLite path for `/feedback` (default `data/feedback.db`) |
| `FEEDBACK_ADMIN_TOKEN` | No | Enables `GET /feedback/admin` via `?token=` or `Authorization: Bearer` |

**Without Twitch variables on the host**, search falls back to **fixture substring matching only** (narrow). Optional **`RAWG_API_KEY`** / **`GIANT_BOMB_API_KEY`** still add merged titles when configured. To match Plan 01 expectations for arbitrary titles, **set Twitch keys in production**.

**Security**

- Never commit `.env`, secrets, or Client Secret to Git.
- Do not expose `TWITCH_CLIENT_SECRET` or eBay secrets to client-side JavaScript or public env dumps.

## Run command (production)

Bind to all interfaces and use the platform’s `PORT`:

```bash
uv run uvicorn game_price_finder.main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

Providers like Render inject `PORT` automatically; locally you can omit it or use `8000`.

## Example: Render.com

These steps are illustrative; check Render’s current UI.

1. **New Web Service** → connect this GitHub repo.
2. **Runtime:** Python **3.12+** (match `requires-python` in [pyproject.toml](pyproject.toml)).
3. **Build command** (install UV then dependencies), e.g.:

   ```bash
   pip install uv && uv sync --frozen
   ```

4. **Start command:**

   ```bash
   uv run uvicorn game_price_finder.main:app --host 0.0.0.0 --port $PORT
   ```

5. **Environment** → add **secret** entries: `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, and optional eBay keys. Set `USE_FIXTURES=false` if you want a cleaner public catalog experience.
6. Deploy, then open the service URL.

Other platforms follow the same pattern: install dependencies with `uv sync --frozen`, run `uvicorn` with `0.0.0.0` and their `PORT`.

## Health check

Configure your load balancer or platform health probe to **`GET /healthz`** (returns JSON `{"status":"ok"}`).

## Operator checklist before sharing the URL

- [ ] `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET` set on the host.
- [ ] `USE_FIXTURES` chosen intentionally for visitor messaging.
- [ ] Optional eBay keys if you want listing aggregation on detail pages.
- [ ] Smoke-test: search a known franchise (e.g. “Elden Ring”), open a result, confirm detail loads.

---

## Optional future: Steam-first catalog without Twitch keys

**Not implemented today.** IGDB requires **server-side** Twitch application credentials; a static or browser-only site cannot safely hold the Client Secret.

If you ever need **broader search without registering a Twitch app**, a possible product direction is:

1. **Search path:** When Twitch keys are absent, call **Steam Store Search** (`steam_store_search` in [game_price_finder/services/steam.py](game_price_finder/services/steam.py)) as the primary hit list instead of IGDB.
2. **Identity:** Rows would be keyed by **Steam `appid`** (not IGDB ids). Detail URLs might become `/games/steam/{app_id}` or use synthetic IDs—this touches [game_price_finder/main.py](game_price_finder/main.py), [fixture_catalog.py](game_price_finder/fixture_catalog.py), and templates.
3. **Pricing:** CheapShark already supports Steam App IDs; Steam `appdetails` can supply storefront overview where applicable.
4. **Tradeoffs:** Weaker normalization vs IGDB (editions/DLC ambiguity), duplicate franchise entries, no automatic IGDB cover/platform aggregation unless added separately.

Treat this as a **follow-on feature** if operators refuse Twitch entirely and accept Steam-centric catalog limits.
