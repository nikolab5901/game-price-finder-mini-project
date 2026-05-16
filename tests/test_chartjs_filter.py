"""Regression tests for Chart.js serialization used by templates."""

from __future__ import annotations

from datetime import UTC, datetime

from game_price_finder.main import templates
from game_price_finder.models import PriceHistoryChart, PriceHistoryDataset, PriceHistoryPoint


def test_chartjs_jinja_filter_handles_none_chart() -> None:
    fn = templates.env.filters["chartjs_json"]
    assert fn(None) == "null"


def test_chartjs_jinja_filter_round_trip_sample_chart() -> None:
    pt = datetime(2026, 1, 15, tzinfo=UTC)
    chart = PriceHistoryChart(
        title="Demo",
        source="cheapshark",
        datasets=[
            PriceHistoryDataset(
                key="k1",
                display_name="Series A",
                points=[PriceHistoryPoint(at=pt, price=19.99)],
            )
        ],
    )
    fn = templates.env.filters["chartjs_json"]
    raw = fn(chart)
    assert raw != "null"
    assert '"labels"' in raw
    assert "Demo" in raw
