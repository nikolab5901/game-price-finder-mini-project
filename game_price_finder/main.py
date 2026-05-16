from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from game_price_finder.config import Settings, get_settings
from game_price_finder.feedback_store import insert_feedback, list_feedback_recent
from game_price_finder.fixture_catalog import fixture_detail, fixture_search
from game_price_finder.models import GamePricingPage, GameSummary, SearchSuggestion, SourceOffer
from game_price_finder.services.catalog_merge import ensure_catalog_nav_urls, merge_catalog_search
from game_price_finder.services.ebay import browse_search_summaries
from game_price_finder.services.giantbomb import giant_bomb_get_game
from game_price_finder.services.igdb import get_game_by_id, search_games_ranked
from game_price_finder.services.pricing import (
    assemble_game_page,
    cheapshark_market_section,
    enrich_fixture_page,
    steam_market_section,
)
from game_price_finder.services.price_history import build_price_history_chart, chartjs_payload
from game_price_finder.services.rawg import rawg_get_game
from game_price_finder.services.research_links import marketplace_query_for_game, research_listing_offers
from game_price_finder.services.search_hints import batch_price_hints_for_games, maybe_fuzzy_suggestions
from game_price_finder.services.steam import apply_steam_cover_fallback, resolve_steam_lookup
from game_price_finder.services.cheapshark import fetch_cheapshark_snapshot

PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
templates.env.filters["urlquote"] = lambda value: quote_plus(str(value))


def _chartjs_json_filter(chart: Any) -> str:
    if chart is None:
        return "null"
    return json.dumps(chartjs_payload(chart))


templates.env.filters["chartjs_json"] = _chartjs_json_filter

app = FastAPI(title="Game Price Finder", version="0.1.0")
app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

ALLOWED_FEEDBACK_CATEGORIES = frozenset({"price_correction", "wrong_game", "feature", "other"})


def settings_dep() -> Settings:
    return get_settings()


def twitch_catalog_ready(settings: Settings) -> bool:
    return bool(settings.twitch_client_id and settings.twitch_client_secret)


def feedback_admin_authorized(settings: Settings, token_query: str | None, authorization: str | None) -> bool:
    expected = settings.feedback_admin_token
    if not expected:
        return False
    candidates: list[str] = []
    if token_query:
        candidates.append(token_query.strip())
    if authorization and authorization.lower().startswith("bearer "):
        candidates.append(authorization[7:].strip())
    return any(c == expected for c in candidates)


async def augment_fixture_page(page: GamePricingPage, settings: Settings) -> GamePricingPage:
    steam_lookup = await resolve_steam_lookup(page.game)
    enriched = apply_steam_cover_fallback(page.game, steam_lookup)
    page = enrich_fixture_page(page, enriched_game=enriched)
    steam_sources, steam_estimates, steam_notes = steam_market_section(steam_lookup)

    prefetch = await fetch_cheapshark_snapshot(enriched)
    cs_sources, cs_estimates, cs_notes = await cheapshark_market_section(enriched, prefetch=prefetch)
    price_chart = await build_price_history_chart(
        enriched,
        settings,
        prefetch=prefetch,
        steam_lookup=steam_lookup,
    )

    urls = {s.url for s in page.sources if s.url}
    steam_extra = [s for s in steam_sources if not s.url or s.url not in urls]
    for s in steam_extra:
        if s.url:
            urls.add(s.url)
    shark_extra = [s for s in cs_sources if not s.url or s.url not in urls]
    for s in shark_extra:
        if s.url:
            urls.add(s.url)

    hub_extra: list[SourceOffer] = []
    for h in research_listing_offers(enriched, include_active_hub=True):
        if h.url and h.url not in urls:
            hub_extra.append(h)
            urls.add(h.url)

    addon_intro = [
        "Demo fixture totals are authored samples — appended Steam/CheapShark sections query live public APIs.",
    ]
    return page.model_copy(
        update={
            "estimates": [*page.estimates, *steam_estimates, *cs_estimates],
            "sources": [*page.sources, *steam_extra, *shark_extra, *hub_extra],
            "methodology_notes": [*page.methodology_notes, *addon_intro, *steam_notes, *cs_notes],
            "price_history_chart": price_chart,
        },
    )


async def _assemble_live_detail(request: Request, game: GameSummary, settings: Settings) -> HTMLResponse:
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

    prefetch = await fetch_cheapshark_snapshot(game)
    cs_sources, cs_estimates, cs_notes = await cheapshark_market_section(game, prefetch=prefetch)
    chart = await build_price_history_chart(
        game,
        settings,
        prefetch=prefetch,
        steam_lookup=steam_lookup,
    )

    page = assemble_game_page(
        game,
        ebay_summaries=ebay_summaries,
        ebay_skip_reason=ebay_skip_reason,
        steam=steam_lookup,
        cheapshark_sources=cs_sources,
        cheapshark_estimates=cs_estimates,
        cheapshark_notes=cs_notes,
        price_history_chart=chart,
    )

    return templates.TemplateResponse(request, "game.html", {"page": page, "settings": settings})


@app.get("/guides", response_class=HTMLResponse)
async def guides_page(request: Request, settings: Settings = Depends(settings_dep)) -> HTMLResponse:
    return templates.TemplateResponse(request, "guides.html", {"settings": settings})


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
    primary_rows: list[GameSummary] = []
    suggestions: list[SearchSuggestion] = []
    price_hints: dict[str, float] = {}

    igdb_hit_count_for_fuzzy = 0

    if twitch_catalog_ready(settings):
        try:
            primary_rows = await search_games_ranked(
                query=q,
                client_id=settings.twitch_client_id or "",
                client_secret=settings.twitch_client_secret or "",
                limit=settings.igdb_search_limit,
            )
        except Exception as exc:  # noqa: BLE001 - surface upstream message to UI
            warnings.append(f"IGDB search failed: {exc}")

        igdb_hit_count_for_fuzzy = len(primary_rows)

        if not primary_rows and not warnings and q.strip():
            warnings.append("No IGDB matches returned — try a shorter title.")
    else:
        primary_rows = fixture_search(q, limit=settings.catalog_merge_max_results) if settings.use_fixtures else []
        igdb_hit_count_for_fuzzy = len(primary_rows)
        if not settings.use_fixtures:
            warnings.append(
                "Twitch / IGDB credentials are missing — set USE_FIXTURES=true for offline demos "
                "or add Twitch keys for catalog search.",
            )
        elif q.strip():
            warnings.append(
                "Fixture demo catalog — franchise-wide IGDB titles require Twitch credentials.",
            )
        if not primary_rows and q.strip():
            warnings.append("No demo titles matched — try clearing the query or search “demo”.")

    if settings.rawg_api_key or settings.giant_bomb_api_key:
        games = await merge_catalog_search(
            query=q,
            primary_rows=primary_rows,
            rawg_api_key=settings.rawg_api_key,
            giant_bomb_api_key=settings.giant_bomb_api_key,
            rawg_limit=settings.catalog_rawg_limit,
            gb_limit=settings.catalog_gb_limit,
            merge_max=settings.catalog_merge_max_results,
        )
    else:
        games = [ensure_catalog_nav_urls(g) for g in primary_rows][: settings.catalog_merge_max_results]

    if games:
        price_hints = await batch_price_hints_for_games(games)
    suggestions = await maybe_fuzzy_suggestions(query=q, igdb_hit_count=igdb_hit_count_for_fuzzy)

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
    primary_rows: list[GameSummary] = []
    if twitch_catalog_ready(settings):
        try:
            primary_rows = await search_games_ranked(
                query=q,
                client_id=settings.twitch_client_id or "",
                client_secret=settings.twitch_client_secret or "",
                limit=settings.catalog_suggestions_igdb_limit,
            )
        except Exception:
            primary_rows = []

    if settings.rawg_api_key or settings.giant_bomb_api_key:
        games = await merge_catalog_search(
            query=q,
            primary_rows=primary_rows,
            rawg_api_key=settings.rawg_api_key,
            giant_bomb_api_key=settings.giant_bomb_api_key,
            rawg_limit=settings.catalog_suggestions_rawg_limit,
            gb_limit=settings.catalog_suggestions_gb_limit,
            merge_max=settings.catalog_suggestions_merge_max,
        )
    else:
        games = [ensure_catalog_nav_urls(g) for g in primary_rows][: settings.catalog_suggestions_merge_max]

    q_strip = q.strip()
    return templates.TemplateResponse(
        request,
        "partials/search_suggestions.html",
        {"games": games, "query_stripped": q_strip},
    )


@app.get("/games/rawg/{rawg_id}", response_class=HTMLResponse)
async def game_detail_rawg(
    request: Request,
    rawg_id: int,
    settings: Settings = Depends(settings_dep),
) -> HTMLResponse:
    if not settings.rawg_api_key:
        raise HTTPException(status_code=404, detail="RAWG catalog not configured.")
    try:
        game = await rawg_get_game(rawg_id=rawg_id, api_key=settings.rawg_api_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"RAWG failed: {exc}") from exc

    if game is None:
        raise HTTPException(status_code=404, detail="Game not found in RAWG.")

    return await _assemble_live_detail(request, game, settings)


@app.get("/games/giantbomb/{guid}", response_class=HTMLResponse)
async def game_detail_giantbomb(
    request: Request,
    guid: str,
    settings: Settings = Depends(settings_dep),
) -> HTMLResponse:
    if not settings.giant_bomb_api_key:
        raise HTTPException(status_code=404, detail="Giant Bomb catalog not configured.")
    try:
        game = await giant_bomb_get_game(guid=guid, api_key=settings.giant_bomb_api_key)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Giant Bomb failed: {exc}") from exc

    if game is None:
        raise HTTPException(status_code=404, detail="Game not found via Giant Bomb.")

    return await _assemble_live_detail(request, game, settings)


@app.get("/games/{igdb_id}", response_class=HTMLResponse)
async def game_detail(
    request: Request,
    igdb_id: int,
    settings: Settings = Depends(settings_dep),
) -> HTMLResponse:
    fixture_page = fixture_detail(igdb_id)
    if fixture_page is not None:
        page = await augment_fixture_page(fixture_page, settings)
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

    return await _assemble_live_detail(request, game, settings)


@app.get("/feedback", response_class=HTMLResponse)
async def feedback_page(
    request: Request,
    game_title: str = Query("", alias="game_title"),
    reference_note: str = Query("", alias="reference_note"),
    settings: Settings = Depends(settings_dep),
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "feedback.html",
        {
            "settings": settings,
            "pref_title": game_title.strip()[:300],
            "pref_reference": reference_note.strip()[:800],
        },
    )


@app.post("/feedback")
async def feedback_submit(
    request: Request,
    category: str = Form(...),
    body: str = Form(...),
    game_title: str = Form(""),
    reference_note: str = Form(""),
    suggested_price_usd: str = Form(""),
    contact_email: str = Form(""),
    website: str = Form(""),
    settings: Settings = Depends(settings_dep),
) -> RedirectResponse:
    honeypot_filled = bool(website.strip())
    cat = category.strip()
    if cat not in ALLOWED_FEEDBACK_CATEGORIES:
        cat = "other"

    price_val: float | None = None
    raw_price = suggested_price_usd.strip()
    if raw_price:
        try:
            price_val = float(raw_price.replace(",", ""))
        except ValueError:
            price_val = None

    if not honeypot_filled:
        insert_feedback(
            db_path=settings.feedback_db_path,
            category=cat,
            body=body,
            game_title=game_title or None,
            reference_note=reference_note or None,
            suggested_price_usd=price_val,
            contact_email=contact_email or None,
            honeypot_filled=False,
        )

    return RedirectResponse(url=request.url_for("feedback_thanks_page"), status_code=303)


@app.get("/feedback/thanks", response_class=HTMLResponse)
async def feedback_thanks_page(request: Request, settings: Settings = Depends(settings_dep)) -> HTMLResponse:
    return templates.TemplateResponse(request, "feedback_thanks.html", {"settings": settings})


@app.get("/feedback/admin", response_class=HTMLResponse)
async def feedback_admin_page(
    request: Request,
    token: str | None = Query(None, alias="token"),
    authorization: str | None = Header(None),
    settings: Settings = Depends(settings_dep),
) -> HTMLResponse:
    if not settings.feedback_admin_token:
        raise HTTPException(status_code=404, detail="Admin feedback view disabled.")
    if not feedback_admin_authorized(settings, token, authorization):
        raise HTTPException(status_code=403, detail="Invalid token.")

    rows = list_feedback_recent(db_path=settings.feedback_db_path, limit=100)
    return templates.TemplateResponse(
        request,
        "feedback_admin.html",
        {"settings": settings, "rows": rows},
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
