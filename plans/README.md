# Project plans

This folder holds **snapshots of Cursor-generated implementation plans** for this repo so you can browse them in Git history, diffs, and PRs without digging through `%USERPROFILE%\.cursor\plans`.

## Index

| Order | File | Summary |
|------:|------|---------|
| 1 | [01-game-price-finder-python-uv.plan.md](01-game-price-finder-python-uv.plan.md) | Initial stack: Python, UV, FastAPI, IGDB/eBay, fixtures, Jinja UI |
| 2 | [02-covers-apis-ui-polish.plan.md](02-covers-apis-ui-polish.plan.md) | Covers + IGDB search improvements, Steam/CheapShark, UI polish |
| 3 | [03-search-franchise-fuzzy-prices.plan.md](03-search-franchise-fuzzy-prices.plan.md) | IGDB-first search when Twitch keys exist; ranked franchise results; fuzzy Steam hints; CheapShark grid hints; HTMX suggestions; fixture/detail routing + copy |
| 4 | [04-more-apis-feedback-sqlite.plan.md](04-more-apis-feedback-sqlite.plan.md) | RAWG + Giant Bomb merged catalog; `detail_path`; SQLite feedback + admin token gate |
| 5 | [05-zero-login-visitor-experience.plan.md](05-zero-login-visitor-experience.plan.md) | Hosted deployment model; visitor vs developer; DEPLOY-oriented docs |
| 6 | [06-user-manual-plans-index.plan.md](06-user-manual-plans-index.plan.md) | USAGE.md user manual; plan 03 snapshot in-repo; plans README index |
| 7 | [07-expand-catalog-coverage.plan.md](07-expand-catalog-coverage.plan.md) | Offline `popular_catalog.json` + generator; configurable IGDB/RAWG/GB merge limits |
| 8 | [08-buyer-seller-information-ux.plan.md](08-buyer-seller-information-ux.plan.md) | `/guides`; IGDB about-panel fields; eBay sold + SteamDB hubs; CheapShark signals; checklists |
| 9 | [09-fixture-cover-artwork.plan.md](09-fixture-cover-artwork.plan.md) | Offline Steam/CheapShark/RAWG thumbnail enrichment for fixture JSON; CSV overrides |
| 10 | [10-price-history-charts.plan.md](10-price-history-charts.plan.md) | Optional ITAD + CheapShark-backed price history chart on game detail (Chart.js) |
| 11 | [11-history-explorer-ui-and-catalog-covers.plan.md](11-history-explorer-ui-and-catalog-covers.plan.md) | Trends-like history explorer UI + Lutris-assisted full `popular_catalog` covers |

## Version history

**Git is the source of truth for history.** Commit updates to this folder when plans change. Cursor may regenerate UUID-stamped files under `.cursor/plans`; when that happens, copy the latest content here (replace or add a dated file if you want to keep multiple revisions).

### Syncing from Cursor (manual)

Cursor typically stores plans under:

`C:\Users\Admin\.cursor\plans\`

Copy relevant `*.plan.md` files into `plans/`, rename with the numbered prefix pattern above, then rewrite absolute paths in links to repo-relative paths (e.g. drop the workspace prefix before `game_price_finder/…`). Commit.
