from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SearchSuggestion(BaseModel):
    """Fuzzy suggestion shown when IGDB returns few/no hits."""

    title: str
    suggested_query: str


class GameSummary(BaseModel):
    """Catalog row — IGDB-native and/or supplemental RAWG / Giant Bomb."""

    igdb_id: int | None = None
    rawg_id: int | None = None
    giant_bomb_guid: str | None = None

    title: str
    platform_summary: str | None = None
    cover_image_url: str | None = None
    release_year: int | None = None
    steam_app_id: int | None = None
    cover_sources: list[str] = Field(default_factory=list)

    genres: list[str] = Field(default_factory=list)
    game_modes: list[str] = Field(default_factory=list)
    short_description: str | None = None
    igdb_slug: str | None = None

    detail_path: str | None = None
    price_hint_key: str | None = None


Channel = Literal["new", "used", "unknown"]
Basis = Literal["sold", "ask"]


class PriceEstimate(BaseModel):
    channel: Channel
    basis: Basis
    currency: str = "USD"
    window_days: int | None = None
    sample_size: int | None = None
    value_usd: float | None = None
    low_usd: float | None = None
    high_usd: float | None = None
    as_of: datetime | None = None
    disclaimer: str | None = None


class SourceOffer(BaseModel):
    source: str
    label: str
    url: str | None = None
    price_usd: float | None = None
    price_low_usd: float | None = None
    price_high_usd: float | None = None
    condition: str | None = None
    fetched_at: datetime | None = None


class SoldBand(BaseModel):
    currency: str = "USD"
    window_days: int = 90
    sample_size: int = 0
    p25_usd: float | None = None
    median_usd: float | None = None
    p75_usd: float | None = None
    basis: Basis = "sold"
    note: str | None = None


PriceHistorySource = Literal["isthereanydeal", "cheapshark"]


class PriceHistoryPoint(BaseModel):
    """Single observation for storefront price history tooling."""

    at: datetime
    price: float
    currency: str = "USD"
    caption: str = ""
    series_key: str = ""


class PriceHistoryDataset(BaseModel):
    key: str
    display_name: str
    points: list[PriceHistoryPoint]


class PriceHistoryInsightRow(BaseModel):
    """Short KPI row for SSR (game detail explorer strip)."""

    label: str
    value: str
    hint: str = ""


class PriceHistoryChart(BaseModel):
    title: str
    footnotes: list[str] = Field(default_factory=list)
    source: PriceHistorySource
    datasets: list[PriceHistoryDataset] = Field(default_factory=list)

    #: UI key: all | 365d | 90d | 30d — used for form default and ITAD fetch.
    history_window_key: str = "all"
    history_window_label: str = "All available"
    #: When False, storefront history cannot be narrowed (CheapShark milestones).
    history_window_adjustable: bool = True

    effective_since: datetime | None = None
    effective_until: datetime | None = None
    insight_rows: list[PriceHistoryInsightRow] = Field(default_factory=list)


class GamePricingPage(BaseModel):
    game: GameSummary
    estimates: list[PriceEstimate] = Field(default_factory=list)
    sources: list[SourceOffer] = Field(default_factory=list)
    sold_band: SoldBand | None = None
    methodology_notes: list[str] = Field(default_factory=list)
    price_history_chart: PriceHistoryChart | None = None


def utcnow() -> datetime:
    return datetime.now(tz=UTC)
