# Plan 12 — Quality assurance (tests, hardened upstream calls, error UX)

Summary of work shipped:

## Defensive upstream handling

- **CheapShark** — [`fetch_cheapshark_snapshot`](game_price_finder/services/cheapshark.py) wraps the full prefetch in `try/except`, logs at warning, returns an empty snapshot so fixture/live pages keep rendering. **`store_id_to_name`** skips caching on failures and returns `{}` instead of propagating HTTP/network errors (with an extra guard in [`cheapshark_market_section`](game_price_finder/services/pricing.py)).
- **Steam** — [`resolve_steam_lookup`](game_price_finder/services/steam.py) catches transport/status errors and returns `None`, matching “no Steam match”.
- **Search** — [`search_page`](game_price_finder/main.py) wraps **`merge_catalog_search`** and **`maybe_fuzzy_suggestions`** in `try/except` with **`warnings`** lines; **`search_suggestions_partial`** falls back gracefully on merge failures.
- **Feedback** — [`feedback_submit`](game_price_finder/main.py) catches **`insert_feedback`** failures and re-renders **`feedback.html`** with a **`submit_error`** banner instead of a bare 500.

## Friendly HTML errors

- **`error.html`** — extends **`base.html`**, status-oriented title, explanation, links (Home / Search / Feedback), **Go back**, optional path for support.
- **Handlers** — [`register_exception_handlers`](game_price_finder/errors.py) installs **`StarletteHTTPException`** (covers routing 404 + FastAPI `HTTPException`) and a catch‑all **`Exception`**: HTML vs JSON driven by **`Accept`**; optional **`settings.debug`** (env **`DEBUG`**) exposes exception summary on unexpected errors.

## Automated tests & packaging

- **Pytest** — optional **`dev`** extra in **`pyproject.toml`**; **`[build-system]`** + Hatchling so **`uv sync`** installs the **`game_price_finder`** package for imports.
- **Tests** — [`tests/conftest.py`](tests/conftest.py) overrides **`settings_dep`** with **`USE_FIXTURES=true`** + temp feedback DB.
- **`tests/`** — catalog JSON validation (**`GamePricingPage.model_validate`**), route smoke (**`/`**, **`/search`**, **`/guides`**, **`/healthz`**, **`/games/900001`**), CheapShark outage simulation ( **`cheapshark_search_games`** raises **`httpx` error**, detail stays **200**), error-page HTML/JSON branching, **`chartjs_json`** filter smoke.

## CI

- **[`.github/workflows/ci.yml`](../.github/workflows/ci.yml)** — **`uv sync --extra dev`** + **`pytest -q`** on push/PR.
