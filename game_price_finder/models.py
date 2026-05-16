from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SearchSuggestion(BaseModel):
    """Fuzzy suggestion shown when IGDB returns few/no hits."""

    title: str
    suggested_query: str


class GameSummary(BaseModel):
    igdb_id: int
    title: str
    platform_summary: str | None = None
    cover_image_url: str | None = None
    release_year: int | None = None
    steam_app_id: int | None = None
    cover_sources: list[str] = Field(default_factory=list)


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


class GamePricingPage(BaseModel):
    game: GameSummary
    estimates: list[PriceEstimate] = Field(default_factory=list)
    sources: list[SourceOffer] = Field(default_factory=list)
    sold_band: SoldBand | None = None
    methodology_notes: list[str] = Field(default_factory=list)


def utcnow() -> datetime:
    return datetime.now(tz=UTC)
