from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from game_price_finder.config import Settings
from game_price_finder.models import (
    GameSummary,
    PriceHistoryChart,
    PriceHistoryDataset,
    PriceHistoryInsightRow,
    PriceHistoryPoint,
    utcnow,
)
from game_price_finder.services.cheapshark import CheapSharkPrefetch, fetch_cheapshark_snapshot, deal_price_usd as cs_deal_price
from game_price_finder.services import isthereanydeal as itad

if TYPE_CHECKING:
    from game_price_finder.services.steam import SteamLookupResult

_MAX_ROWS_PER_HISTORY = 400
_MAX_SHOPS_SERIES = 10
_HISTORY_SINCE_YEAR_FALLBACK = 2008

_HISTORY_WINDOW_KEYS = frozenset({"all", "30d", "90d", "365d"})


def normalize_history_window_key(raw: str | None) -> str:
    """Return all | 30d | 90d | 365d."""
    if not raw or not isinstance(raw, str):
        return "all"
    k = raw.strip().lower()
    return k if k in _HISTORY_WINDOW_KEYS else "all"


def history_window_delta(key: str) -> timedelta | None:
    return {
        "all": None,
        "30d": timedelta(days=30),
        "90d": timedelta(days=90),
        "365d": timedelta(days=365),
    }.get(key, None)


def history_window_label(key: str) -> str:
    return {
        "all": "All available",
        "30d": "Past 30 days",
        "90d": "Past 90 days",
        "365d": "Past year",
    }.get(key, "All available")


def _effective_since_bound(
    *,
    release_floor: datetime,
    history_window_key: str,
    now: datetime,
) -> datetime:
    delta = history_window_delta(history_window_key)
    if delta is None:
        return release_floor
    return max(release_floor, now - delta)


def _chart_insights(
    chart: PriceHistoryChart,
) -> tuple[datetime | None, datetime | None, list[PriceHistoryInsightRow]]:
    all_pts: list[PriceHistoryPoint] = []
    for ds in chart.datasets:
        all_pts.extend(ds.points)
    if not all_pts:
        return None, None, []

    span_start = min(p.at for p in all_pts)
    span_end = max(p.at for p in all_pts)
    atl = min(all_pts, key=lambda p: p.price)
    latest = max(all_pts, key=lambda p: p.at)

    if chart.source == "cheapshark":
        rows = [
            PriceHistoryInsightRow(
                label="Recorded low (API)",
                value=f"${atl.price:.2f}",
                hint=atl.at.strftime("%Y-%m-%d %H:%M UTC"),
            ),
            PriceHistoryInsightRow(
                label="Latest snapshot",
                value=f"${latest.price:.2f}",
                hint=latest.at.strftime("%Y-%m-%d %H:%M UTC"),
            ),
            PriceHistoryInsightRow(
                label="Span",
                value=f"{span_start.strftime('%Y-%m-%d')} → {span_end.strftime('%Y-%m-%d')}",
                hint="CheapShark exposes sparse milestones, not a full curve.",
            ),
        ]
    else:
        rows = [
            PriceHistoryInsightRow(
                label="Low in view (USD)",
                value=f"${atl.price:.2f}",
                hint=(atl.caption or "").strip() or atl.at.strftime("%Y-%m-%d %H:%M UTC"),
            ),
            PriceHistoryInsightRow(
                label="Latest observation",
                value=f"${latest.price:.2f}",
                hint=latest.at.strftime("%Y-%m-%d %H:%M UTC"),
            ),
            PriceHistoryInsightRow(
                label="Storefront series",
                value=str(len(chart.datasets)),
                hint="Shops with the most logged price changes (capped).",
            ),
            PriceHistoryInsightRow(
                label="Data points",
                value=str(len(all_pts)),
                hint="After server-side sampling for chart size.",
            ),
            PriceHistoryInsightRow(
                label="Span (UTC)",
                value=f"{span_start.strftime('%Y-%m-%d')} → {span_end.strftime('%Y-%m-%d')}",
                hint="IsThereAnyDeal storefront log",
            ),
        ]
    return span_start, span_end, rows


def _finalize_chart_window_meta(
    chart: PriceHistoryChart,
    *,
    history_window_key: str,
    history_window_adjustable: bool,
) -> PriceHistoryChart:
    eff_lo, eff_hi, rows = _chart_insights(chart)
    return chart.model_copy(
        update={
            "history_window_key": history_window_key,
            "history_window_label": history_window_label(history_window_key),
            "history_window_adjustable": history_window_adjustable,
            "effective_since": eff_lo,
            "effective_until": eff_hi,
            "insight_rows": rows,
        }
    )


def _utc_label(dt: datetime) -> str:
    u = dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    z = u.astimezone(UTC)
    return z.isoformat().replace("+00:00", "Z")


def _downsample_points(points_sorted: list[PriceHistoryPoint], max_n: int) -> list[PriceHistoryPoint]:
    if len(points_sorted) <= max_n:
        return points_sorted
    step = (len(points_sorted) - 1) / (max_n - 1)
    out: list[PriceHistoryPoint] = []
    for i in range(max_n):
        idx = int(round(i * step))
        idx = min(idx, len(points_sorted) - 1)
        out.append(points_sorted[idx])
    return out


def _hsl_for_series_key(series_key: str) -> str:
    h = abs(hash(series_key)) % 360
    return f"hsl({h}, 42%, 48%)"


def chartjs_payload(chart: PriceHistoryChart) -> dict[str, Any]:
    """Align datasets to sorted union timestamps for categorical Chart.js axes."""
    label_set: set[str] = set()
    for ds in chart.datasets:
        for p in ds.points:
            label_set.add(_utc_label(p.at))
    labels = sorted(label_set)
    index_lookup = {lab: idx for idx, lab in enumerate(labels)}
    datasets: list[dict[str, Any]] = []
    for ds in chart.datasets:
        values: list[float | None] = [None] * len(labels)
        for p in ds.points:
            lab = _utc_label(p.at)
            i = index_lookup.get(lab)
            if i is None:
                continue
            values[i] = float(p.price)
        datasets.append(
            {
                "label": ds.display_name,
                "key": ds.key,
                "borderColor": _hsl_for_series_key(ds.key),
                "backgroundColor": "transparent",
                "data": values,
                "spanGaps": True,
                "pointRadius": 2,
                "tension": 0.15,
            }
        )
    return {
        "title": chart.title,
        "source": chart.source,
        "footnotes": chart.footnotes,
        "labels": labels,
        "datasets": datasets,
    }


def _cheapshark_milestone_chart(
    *,
    game_title: str,
    bundle: dict[str, Any] | None,
    deals: list[dict[str, Any]],
) -> PriceHistoryChart | None:
    now = utcnow()
    milestones: list[PriceHistoryPoint] = []

    cpe: dict[str, Any] | None = None
    if isinstance(bundle, dict):
        raw = bundle.get("cheapestPriceEver")
        cpe = raw if isinstance(raw, dict) else None
    ever_price: float | None = None
    ever_at = now
    ever_price_raw = cpe.get("price") if cpe else None
    ever_ts_raw = cpe.get("date") if cpe else None
    if ever_price_raw is not None:
        try:
            ep = float(ever_price_raw)
        except (TypeError, ValueError):
            ep = None
        if ep is not None:
            ever_price = ep
            if ever_ts_raw is not None:
                try:
                    ever_at = datetime.fromtimestamp(int(ever_ts_raw), tz=UTC)
                except (TypeError, ValueError, OSError):
                    ever_at = now
            milestones.append(
                PriceHistoryPoint(
                    at=ever_at,
                    price=ever_price,
                    currency="USD",
                    caption=f"CheapShark-recorded lowest PC deal (${ever_price:.2f}).",
                    series_key="cheapshark_milestones",
                )
            )

    floor_candidates: list[float] = []
    for d in deals[:40]:
        p = cs_deal_price(d)
        if p is not None:
            floor_candidates.append(p)
    current_best = min(floor_candidates) if floor_candidates else None
    if current_best is None and isinstance(bundle, dict):
        cheapest_text = bundle.get("cheapest")
        if cheapest_text is not None:
            try:
                current_best = float(cheapest_text)
            except (TypeError, ValueError):
                current_best = None

    snap_price = current_best if current_best is not None else ever_price
    if current_best is not None:
        snap_caption = "Best storefront deal scanned in this response."
    elif ever_price is not None:
        snap_caption = (
            "Snapshot uses recorded all-time tracker value (no newer floor in scanned deals)."
        )
    else:
        snap_caption = ""
    if snap_price is not None:
        milestones.append(
            PriceHistoryPoint(
                at=now,
                price=float(snap_price),
                currency="USD",
                caption=snap_caption or "CheapShark storefront snapshot.",
                series_key="cheapshark_milestones",
            )
        )

    if snap_price is None:
        return None
    milestones.sort(key=lambda p: p.at)
    if len(milestones) < 2:
        return None
    distinct_ts = {_utc_label(p.at) for p in milestones}
    if len(distinct_ts) < 2:
        last = milestones[-1]
        milestones[-1] = last.model_copy(update={"at": last.at + timedelta(seconds=1)})
        milestones.sort(key=lambda p: p.at)

    ds = PriceHistoryDataset(
        key="cheapshark_milestones",
        display_name="CheapShark milestones (sparse)",
        points=sorted(milestones, key=lambda p: p.at),
    )
    footnotes = [
        "Only two CheapShark milestones are available from the public API (all-time tracked low + current scan) — not a continuous price curve.",
        "Digital promo prices differ from physical resale; treat as orientation for PC storefront deals only.",
    ]
    return PriceHistoryChart(
        title=f"Tracked PC deal milestones — {game_title}",
        footnotes=footnotes,
        source="cheapshark",
        datasets=[ds],
    )


def _itad_history_chart(
    *,
    game_title: str,
    raw_rows: list[dict[str, Any]],
    country: str,
) -> PriceHistoryChart | None:
    buckets: dict[int, list[tuple[str, PriceHistoryPoint]]] = defaultdict(list)
    for row in raw_rows[: _MAX_ROWS_PER_HISTORY * 2]:
        ts = itad.parse_history_timestamp(row.get("timestamp"))
        if ts is None:
            continue
        price, currency = itad.history_row_sale_price(row)
        if price is None or currency != "USD":
            continue
        shop = row.get("shop") if isinstance(row.get("shop"), dict) else {}
        sid_raw = shop.get("id")
        sname = shop.get("name")
        try:
            sid = int(sid_raw)
        except (TypeError, ValueError):
            sid = -1
        label = str(sname) if isinstance(sname, str) and sname.strip() else f"Shop {sid}"
        sk = f"shop_{sid}"
        buckets[sid].append(
            (
                label,
                PriceHistoryPoint(
                    at=ts,
                    price=price,
                    currency=currency,
                    caption=f"{label} · ${price:.2f} {currency}",
                    series_key=sk,
                ),
            )
        )

    if not buckets:
        return None

    ranked = sorted(buckets.items(), key=lambda kv: len(kv[1]), reverse=True)[:_MAX_SHOPS_SERIES]
    datasets: list[PriceHistoryDataset] = []
    for sid, labelled_pts in ranked:
        labels_pts = sorted(labelled_pts, key=lambda pair: pair[1].at)
        pts_sorted = [p for _lb, p in labels_pts]
        pts_ds = _downsample_points(pts_sorted, _MAX_ROWS_PER_HISTORY // max(1, len(ranked)))
        disp = labels_pts[0][0]
        datasets.append(
            PriceHistoryDataset(
                key=f"shop_{sid}",
                display_name=disp,
                points=pts_ds,
            )
        )

    footnotes = [
        f"IsThereAnyDeal history for country {country} — USD rows only. Console editions and disc resale are not represented.",
        "History reflects tracked authorized storefront price changes, not every discount or bundle nuance.",
    ]
    return PriceHistoryChart(
        title=f"Storefront price log — {game_title}",
        footnotes=footnotes,
        source="isthereanydeal",
        datasets=datasets,
    )


async def build_price_history_chart(
    game: GameSummary,
    settings: Settings,
    *,
    prefetch: CheapSharkPrefetch | None = None,
    steam_lookup: SteamLookupResult | None = None,
    history_window_raw: str | None = None,
) -> PriceHistoryChart | None:
    """Prefer ITAD when configured + Steam id; otherwise CheapShark milestone chart."""
    win_key = normalize_history_window_key(history_window_raw)

    if prefetch is not None:
        deals, _picked, bundle = prefetch
    else:
        deals, _picked, bundle = await fetch_cheapshark_snapshot(game)

    country = "US"
    api_key = settings.itad_api_key
    steam_id = game.steam_app_id
    if steam_lookup is not None and steam_lookup.app_id:
        steam_id = steam_lookup.app_id

    if api_key and steam_id is not None:
        try:
            gid = await itad.lookup_itad_uuid_for_steam_app(steam_app_id=int(steam_id), api_key=api_key)
        except Exception:  # noqa: BLE001
            gid = None
        if gid:
            since_year = game.release_year or _HISTORY_SINCE_YEAR_FALLBACK
            release_floor = datetime(since_year, 1, 1, tzinfo=UTC)
            now = utcnow()
            since_eff = _effective_since_bound(
                release_floor=release_floor,
                history_window_key=win_key,
                now=now,
            )
            try:
                raw = await itad.fetch_price_history_log(
                    game_uuid=gid,
                    api_key=api_key,
                    country=country,
                    since=since_eff,
                )
            except Exception:  # noqa: BLE001
                raw = []
            chart = _itad_history_chart(game_title=game.title, raw_rows=raw, country=country)
            if chart is not None:
                return _finalize_chart_window_meta(
                    chart,
                    history_window_key=win_key,
                    history_window_adjustable=True,
                )

    cs_chart = _cheapshark_milestone_chart(game_title=game.title, bundle=bundle, deals=deals)
    if cs_chart is None:
        return None
    return _finalize_chart_window_meta(
        cs_chart,
        history_window_key=win_key,
        history_window_adjustable=False,
    )
