# Project plans

This folder holds **snapshots of Cursor-generated implementation plans** for this repo so you can browse them in Git history, diffs, and PRs without digging through `%USERPROFILE%\.cursor\plans`.

## Index

| Order | File | Summary |
|------:|------|---------|
| 1 | [01-game-price-finder-python-uv.plan.md](01-game-price-finder-python-uv.plan.md) | Initial stack: Python, UV, FastAPI, IGDB/eBay, fixtures, Jinja UI |
| 2 | [02-covers-apis-ui-polish.plan.md](02-covers-apis-ui-polish.plan.md) | Covers + IGDB search improvements, Steam/CheapShark, UI polish |
| 3 | [03-search-franchise-fuzzy-prices.plan.md](03-search-franchise-fuzzy-prices.plan.md) | IGDB-first search when Twitch keys exist; ranked franchise results; fuzzy Steam hints; CheapShark grid hints; HTMX suggestions; fixture/detail routing + copy |

## Version history

**Git is the source of truth for history.** Commit updates to this folder when plans change. Cursor may regenerate UUID-stamped files under `.cursor/plans`; when that happens, copy the latest content here (replace or add a dated file if you want to keep multiple revisions).

### Syncing from Cursor (manual)

Cursor typically stores plans under:

`C:\Users\Admin\.cursor\plans\`

Copy relevant `*.plan.md` files into `plans/`, rename with the numbered prefix pattern above, then commit.
