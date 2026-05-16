from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from game_price_finder.models import GameSummary

TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_BASE = "https://api.igdb.com/v4"

# IGDB external_game_category: Steam corresponds to enum value 1.
_STEAM_EXTERNAL_CATEGORY = 1

IGDB_TEMPLATE_RE = re.compile(r"/t_[a-z0-9]+/")


def _sanitize_search_term(term: str) -> str:
    cleaned = term.replace('"', "").replace("*", "").replace(";", "").strip()
    return cleaned[:120]


def _normalize_cover_url(raw: str | None) -> str | None:
    if not raw:
        return None
    if raw.startswith("//"):
        return f"https:{raw}"
    return raw


def cover_url_best_effort(
    *,
    cover_url: str | None,
    image_id: Any,
) -> tuple[str | None, list[str]]:
    """Prefer IGDB CDN URLs upgraded to t_cover_big; fall back to image_id."""
    provenance: list[str] = []
    if cover_url:
        base = _normalize_cover_url(cover_url)
        if not base:
            return None, []
        upgraded = IGDB_TEMPLATE_RE.sub("/t_cover_big/", base)
        provenance.append("igdb:cover_big" if upgraded != base else "igdb:cover")
        return upgraded, provenance
    if image_id is None:
        return None, []
    ident = str(image_id).strip()
    if not ident:
        return None, []
    return (
        f"https://images.igdb.com/igdb/image/upload/t_cover_big/{ident}.jpg",
        ["igdb:image_id"],
    )


def _external_category_value(category: Any) -> int | None:
    if category is None:
        return None
    if isinstance(category, dict):
        raw = category.get("id") if category.get("id") is not None else category.get("value")
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None
    try:
        return int(category)
    except (TypeError, ValueError):
        return None


def extract_steam_app_id(external_games: Any) -> int | None:
    if not isinstance(external_games, list):
        return None
    for eg in external_games:
        if not isinstance(eg, dict):
            continue
        if _external_category_value(eg.get("category")) != _STEAM_EXTERNAL_CATEGORY:
            continue
        uid = eg.get("uid")
        if uid is None:
            continue
        try:
            return int(str(uid).strip())
        except ValueError:
            continue
    return None


async def fetch_twitch_app_access_token(client_id: str, client_secret: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            TWITCH_TOKEN_URL,
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
        )
        response.raise_for_status()
        data = response.json()
        return str(data["access_token"])


async def igdb_post(
    endpoint: str,
    *,
    body: str,
    client_id: str,
    access_token: str,
) -> list[Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{IGDB_BASE}/{endpoint}",
            headers={
                "Client-ID": client_id,
                "Authorization": f"Bearer {access_token}",
            },
            content=body.encode("utf-8"),
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else []


def _platform_summary(platforms: Any) -> str | None:
    if not isinstance(platforms, list) or not platforms:
        return None
    names: list[str] = []
    for p in platforms[:4]:
        if isinstance(p, dict) and p.get("name"):
            names.append(str(p["name"]))
    return ", ".join(names) if names else None


def _game_summary_from_payload(row: dict[str, Any]) -> GameSummary | None:
    gid = row.get("id")
    name = row.get("name")
    if gid is None or not name:
        return None
    release_year = None
    ts = row.get("first_release_date")
    if isinstance(ts, int):
        release_year = datetime.fromtimestamp(ts, tz=UTC).year

    cover = row.get("cover")
    raw_cover_url = None
    image_id = None
    if isinstance(cover, dict):
        raw_cover_url = cover.get("url")
        image_id = cover.get("image_id")
    cover_image_url, cover_sources = cover_url_best_effort(cover_url=raw_cover_url, image_id=image_id)

    steam_app_id = extract_steam_app_id(row.get("external_games"))

    return GameSummary(
        igdb_id=int(gid),
        title=str(name),
        platform_summary=_platform_summary(row.get("platforms")),
        cover_image_url=cover_image_url,
        release_year=release_year,
        steam_app_id=steam_app_id,
        cover_sources=cover_sources or None,
    )


def _game_fields_line() -> str:
    return (
        "fields id,name,cover.url,cover.image_id,first_release_date,platforms.name,"
        "external_games.uid,external_games.category,rating_count;\n"
    )


def _rating_count(row: dict[str, Any]) -> int:
    raw = row.get("rating_count")
    try:
        return int(raw) if raw is not None else 0
    except (TypeError, ValueError):
        return 0


def _rank_fts_then_popular_wildcard(
    rows_search: list[dict[str, Any]],
    rows_wild: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    fts_order: list[int] = []
    by_id: dict[int, dict[str, Any]] = {}
    for row in rows_search:
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        gid = int(row["id"])
        if gid not in by_id:
            by_id[gid] = row
            fts_order.append(gid)

    fts_ids = set(fts_order)
    wild_seen: set[int] = set()
    wild_unique: list[dict[str, Any]] = []
    for row in rows_wild:
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        gid = int(row["id"])
        if gid in fts_ids or gid in wild_seen:
            continue
        wild_seen.add(gid)
        wild_unique.append(row)

    wild_unique.sort(key=_rating_count, reverse=True)

    ordered: list[dict[str, Any]] = [by_id[i] for i in fts_order]
    ordered.extend(wild_unique)
    return ordered[:limit]


async def search_games(
    *,
    query: str,
    client_id: str,
    client_secret: str,
    limit: int = 30,
) -> list[GameSummary]:
    term = _sanitize_search_term(query)
    if not term:
        return []

    token = await fetch_twitch_app_access_token(client_id, client_secret)
    safe = term.replace("\\", "").replace("*", "")
    needle = safe.lower()

    search_body = (
        f'search "{safe}";\n'
        f"{_game_fields_line()}"
        f"limit {limit};\n"
    )
    wildcard_body = (
        f'where name ~ *"{needle}"*;\n'
        f"{_game_fields_line()}"
        f"limit {limit};\n"
    )

    rows_search = await igdb_post("games", body=search_body, client_id=client_id, access_token=token)
    rows_wild: list[Any] = []
    try:
        rows_wild = await igdb_post("games", body=wildcard_body, client_id=client_id, access_token=token)
    except httpx.HTTPStatusError:
        rows_wild = []

    merged_rows = _rank_fts_then_popular_wildcard(
        [r for r in rows_search if isinstance(r, dict)],
        [r for r in rows_wild if isinstance(r, dict)],
        limit=limit,
    )
    games: list[GameSummary] = []
    for row in merged_rows:
        summary = _game_summary_from_payload(row)
        if summary:
            games.append(summary)
    return games


search_games_ranked = search_games


async def get_game_by_id(
    *,
    igdb_id: int,
    client_id: str,
    client_secret: str,
) -> GameSummary | None:
    token = await fetch_twitch_app_access_token(client_id, client_secret)
    body = (
        f"{_game_fields_line()}"
        f'where id = {int(igdb_id)};\n'
        "limit 1;\n"
    )
    rows = await igdb_post("games", body=body, client_id=client_id, access_token=token)
    if not rows or not isinstance(rows[0], dict):
        return None
    return _game_summary_from_payload(rows[0])
