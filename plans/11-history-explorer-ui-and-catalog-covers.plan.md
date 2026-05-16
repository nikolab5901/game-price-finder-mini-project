---
name: History explorer UI + catalog covers
overview: Restyle price history into a Trends-like explorer with timeframe query support, Lutris-assisted full offline cover thumbnails, generator merge hooks, and documentation.
---

# History chart UI + 100% bundled catalog covers

## Price history explorer

- Model [`game_price_finder/models.py`](../game_price_finder/models.py) adds **`PriceHistoryInsightRow`** plus chart metadata (**`history_window_key`**, **`insight_rows`**, effective span, **`history_window_adjustable`**).
- [`game_price_finder/services/price_history.py`](../game_price_finder/services/price_history.py) computes **`since_eff`** for IsThereAnyDeal from release floor vs **`history_window`** (`all`, `365d`, `90d`, `30d`), enriches charts with KPI strips, keeps CheapShark milestone path non-adjustable in the UI sense.
- Live detail handlers in [`game_price_finder/main.py`](../game_price_finder/main.py) accept **`history_window`** query and forward it into **`build_price_history_chart`**.
- [`game_price_finder/templates/game.html`](../game_price_finder/templates/game.html) lifts the explorer **above** average estimates after the hero/about block: toolbar **`GET`** form against the current URL, insight tiles, optional series chips toggling **`Chart.js`** dataset visibility, grid styling, **`details`** fallback table.

## Offline catalog artwork

- **`scripts/cover_fallbacks_override.json`** — Steam header URLs plus Lutris **`/api/games`** search results (proxy IGDB-hosted `coverart` thumbnails). Curated tails for ambiguous Lutris lookups (e.g. dual-title Pokémon packs use Scarlet art).
- [`scripts/populate_cover_fallbacks_lutris.py`](../scripts/populate_cover_fallbacks_lutris.py) refreshes fallbacks while respecting existing Steam overrides.
- [`scripts/generate_popular_catalog.py`](../scripts/generate_popular_catalog.py) merges fallbacks (`--cover-fallbacks-json`, **`--fail-on-missing-covers`**).
- [`scripts/patch_catalog_covers_from_fallbacks.py`](../scripts/patch_catalog_covers_from_fallbacks.py) rewrites **`popular_catalog.json`** when generator output was rebuilt from CSV-only.
