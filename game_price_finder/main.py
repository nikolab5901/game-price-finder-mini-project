from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from game_price_finder.config import Settings, get_settings
from game_price_finder.fixture_catalog import fixture_detail, fixture_search
from game_price_finder.models import GamePricingPage, GameSummary, SearchSuggestion
from game_price_finder.services.ebay import browse_search_summaries
from game_price_finder.services.igdb import get_game_by_id, search_games_ranked
from game_price_finder.services.pricing import (
    assemble_game_page,
    cheapshark_market_section,
    enrich_fixture_page,
    marketplace_query_for_game,
    steam_market_section,
)
from game_price_finder.services.search_hints import batch_price_hints_for_games, maybe_fuzzy_suggestions
from game_price_finder.services.steam import apply_steam_cover_fallback, resolve_steam_lookup

PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
templates.env.filters["urlquote"] = lambda value: quote_plus(str(value))

app = FastAPI(title="Game Price Finder", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")


def settings_dep() -> Settings:
    return get_settings()


def twitch_catalog_ready(settings: Settings) -> bool:
    return bool(settings.twitch_client_id and settings.twitch_client_secret)


async def augment_fixture_page(page: GamePricingPage) -> GamePricingPage:
    steam_lookup = await resolve_steam_lookup(page.game)
    enriched = apply_steam_cover_fallback(page.game, steam_lookup)
    page = enrich_fixture_page(page, enriched_game=enriched)
    steam_sources, steam_estimates, steam_notes = steam_market_section(steam_lookup)
    cs_sources, cs_estimates, cs_notes = await cheapshark_market_section(enriched)

    urls = {s.url for s in page.sources if s.url}
    steam_extra = [s for s in steam_sources if not s.url or s.url not in urls]
    shark_extra = [s for s in cs_sources if not s.url or s.url not in urls]

    addon_intro = [
        "Demo fixture totals are authored samples — appended Steam/CheapShark sections query live public APIs.",
    ]
    return page.model_copy(
        update={
            "estimates": [*page.estimates, *steam_estimates, *cs_estimates],
            "sources": [*page.sources, *steam_extra, *shark_extra],
            "methodology_notes": [*page.methodology_notes, *addon_intro, *steam_notes, *cs_notes],
        },
    )


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, settings: Settings = Depends(settings_dep)) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "index.html",
        {"settings": settings, "twitch_catalog_ready": twitch_catalog_ready(settings)},
    )


@app.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = Query("", alias="q"),
    settings: Settings = Depends(settings_dep),
) -> HTMLResponse:
    warnings: list[str] = []
    games: list[GameSummary] = []
    suggestions: list[SearchSuggestion] = []
    price_hints: dict[int, float] = {}

    if twitch_catalog_ready(settings):
        try:
            games = await search_games_ranked(
                query=q,
                client_id=settings.twitch_client_id or "",
                client_secret=settings.twitch_client_secret or "",
            )
        except Exception as exc:  # noqa: BLE001 - surface upstream message to UI
            warnings.append(f"IGDB search failed: {exc}")

        if games:
            price_hints = await batch_price_hints_for_games(games)
        suggestions = await maybe_fuzzy_suggestions(query=q, igdb_hit_count=len(games))

        if not games and not warnings and q.strip():
            warnings.append("No IGDB matches returned — try a shorter title.")
    else:
        games = fixture_search(q) if settings.use_fixtures else []
        if not settings.use_fixtures:
            warnings.append(
                "Twitch / IGDB credentials are missing — set USE_FIXTURES=true for offline demos "
                "or add Twitch keys for catalog search.",
            )
        elif q.strip():
            warnings.append(
                "Fixture demo catalog — franchise-wide IGDB titles require Twitch credentials.",
            )
        if not games and q.strip():
            warnings.append("No demo titles matched — try clearing the query or search “demo”.")

    return templates.TemplateResponse(
        request,
        "search.html",
        {
            "query": q,
            "games": games,
            "warnings": warnings,
            "settings": settings,
            "suggestions": suggestions,
            "price_hints": price_hints,
            "twitch_catalog_ready": twitch_catalog_ready(settings),
        },
    )


@app.get("/partials/search-suggestions", response_class=HTMLResponse)
async def search_suggestions_partial(
    request: Request,
    q: str = Query("", alias="q"),
    settings: Settings = Depends(settings_dep),
) -> HTMLResponse:
    games: list[GameSummary] = []
    if twitch_catalog_ready(settings):
        try:
            games = await search_games_ranked(
                query=q,
                client_id=settings.twitch_client_id or "",
                client_secret=settings.twitch_client_secret or "",
                limit=8,
            )
        except Exception:
            games = []

    q_strip = q.strip()
    return templates.TemplateResponse(
        request,
        "partials/search_suggestions.html",
        {"games": games, "query_stripped": q_strip},
    )


@app.get("/games/{igdb_id}", response_class=HTMLResponse)
async def game_detail(
    request: Request,
    igdb_id: int,
    settings: Settings = Depends(settings_dep),
) -> HTMLResponse:
    fixture_page = fixture_detail(igdb_id)
    if fixture_page is not None:
        page = await augment_fixture_page(fixture_page)
        return templates.TemplateResponse(request, "game.html", {"page": page, "settings": settings})

    if not twitch_catalog_ready(settings):
        raise HTTPException(
            status_code=404,
            detail="Catalog title not available offline — configure Twitch credentials for IGDB or open a demo fixture ID.",
        )

    try:
        game = await get_game_by_id(
            igdb_id=igdb_id,
            client_id=settings.twitch_client_id or "",
            client_secret=settings.twitch_client_secret or "",
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"IGDB failed: {exc}") from exc

    if game is None:
        raise HTTPException(status_code=404, detail="Game not found in IGDB.")

    steam_lookup = await resolve_steam_lookup(game)
    game = apply_steam_cover_fallback(game, steam_lookup)

    ebay_summaries: list[dict[str, Any]] = []
    ebay_skip_reason: str | None = None
    if settings.ebay_client_id and settings.ebay_client_secret:
        query = marketplace_query_for_game(game)
        try:
            ebay_summaries = await browse_search_summaries(settings=settings, search_query=query)
        except Exception as exc:  # noqa: BLE001
            ebay_skip_reason = f"eBay Browse API failed: {exc}"
    else:
        ebay_skip_reason = "eBay developer credentials not configured — Browse API aggregation skipped."

    cs_sources, cs_estimates, cs_notes = await cheapshark_market_section(game)

    page = assemble_game_page(
        game,
        ebay_summaries=ebay_summaries,
        ebay_skip_reason=ebay_skip_reason,
        steam=steam_lookup,
        cheapshark_sources=cs_sources,
        cheapshark_estimates=cs_estimates,
        cheapshark_notes=cs_notes,
    )

    return templates.TemplateResponse(request, "game.html", {"page": page, "settings": settings})


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
