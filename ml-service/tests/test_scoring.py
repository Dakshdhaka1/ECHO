"""Health-score engine invariants (SCORING.md §3-4)."""

from datetime import date

import numpy as np
import pytest

import pandas as pd

from app.inference.scoring import ScoringInputs, band_for, market_metrics, score_company


def inputs(**overrides) -> ScoringInputs:
    base = dict(
        as_of=date(2025, 6, 30), sector="Information Technology", is_bank=False,
        features={"altman_z2": 3.0, "piotroski_f": 7.0, "revenue_yoy": 0.1, "net_margin": 0.15, "current_ratio": 1.6,
                  "debt_equity": 0.4, "fcf_margin": 0.12, "negative_equity": 0.0},
        peer_table={}, peer_table_date=None, financial_freshness=1.0, financial_evidence=["ev:x"], events=[],
        news=None, market=None, employee=None)
    base.update(overrides)
    return ScoringInputs(**base)


def peer_table():
    """Uniform peers: quantiles 0..1 for every factor, so percentile == value clipped to [0, 1]."""
    q = np.linspace(0, 1, 101)
    feats = ["altman_z2", "revenue_yoy", "net_margin", "current_ratio", "debt_equity", "fcf_margin"]
    return {("ALL", f): (500, q) for f in feats}


def test_attribution_sums_exactly_to_score_minus_50():
    health, pillars, _ = score_company(inputs(peer_table=peer_table()), {})
    total_impact = sum(f.impact for p in pillars for f in p.factors)
    assert health.override is None
    assert 50 + total_impact == pytest.approx(health.raw_score, abs=0.01)


def test_missing_pillars_renormalise_weights_and_lower_confidence():
    health, pillars, _ = score_company(inputs(peer_table=peer_table()), {"market": "no prices", "news": "none"})
    used = [p for p in pillars if p.score is not None]
    assert sum(p.effective_weight for p in used) == pytest.approx(1.0, abs=1e-3)
    assert next(p for p in pillars if p.key == "market").unavailable_reason == "no prices"
    assert health.confidence < 0.75


def test_bankruptcy_event_caps_the_score():
    ev = [{"id": "e", "date": date(2025, 6, 1), "type": "BANKRUPTCY", "label": "Bankruptcy", "origin": "8-K Item 1.03",
           "severity": "CRITICAL", "penalty": 100.0, "cap": 10.0, "title": "", "evidence": []}]
    health, pillars, _ = score_company(inputs(peer_table=peer_table(), events=ev), {})
    assert health.score is not None and health.score <= 10
    assert "capped" in health.override


def test_insufficient_data_returns_no_score():
    health, _, _ = score_company(inputs(features={}, financial_freshness=0.0), {"financial": "no XBRL"})
    assert health.score is None and health.band == "INSUFFICIENT_DATA"


def test_bands():
    assert [band_for(s) for s in (85, 60, 45, 30, 10)] == ["STRONG", "STABLE", "WATCH", "WEAK", "CRITICAL"]


def test_distress_zone_guard_rail_caps_factor():
    _, pillars, _ = score_company(inputs(peer_table=peer_table(), features={**inputs().features, "altman_z2": 0.5}), {})
    z = next(f for f in pillars[0].factors if f.key == "altman_z2")
    assert z.score <= 20 and "distress zone" in z.note


def test_market_metrics_from_weekly_history_with_excess_return():
    idx = pd.date_range("2024-01-05", periods=80, freq="W-FRI")
    stock = pd.DataFrame({"close": [100 * 1.01 ** i for i in range(80)], "volume": 1e6}, index=idx)
    etf = pd.DataFrame({"close": [100 * 1.005 ** i for i in range(80)], "volume": 1e6}, index=idx)
    m = market_metrics(None, stock, etf, idx[-1].date())
    assert m["basis"] == "weekly adjusted close"
    assert m["return_12m"] == pytest.approx(1.01 ** 52 - 1)
    assert m["excess_12m"] == pytest.approx((1.01 ** 52 - 1) - (1.005 ** 52 - 1))
    assert m["drawdown_52w"] == pytest.approx(0.0)
    assert market_metrics(None, stock, etf, (idx[-1] + pd.Timedelta(days=30)).date()) is None  # stale prices
