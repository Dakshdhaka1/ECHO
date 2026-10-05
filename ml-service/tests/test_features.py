"""Point-in-time feature builder: ratio math, Q4 derivation and leakage control (ML_PIPELINE §6)."""

import numpy as np
import pandas as pd
import pytest

from pipelines.features import financial


def fact(item, end, val, filed, start=None, rank=0):
    return {"item": item, "rank": rank, "start": pd.Timestamp(start) if start else pd.NaT, "end": pd.Timestamp(end),
            "val": float(val), "fy": None, "fp": None, "form": "10-K", "filed": pd.Timestamp(filed), "accn": "x"}


@pytest.fixture
def facts():
    rows = [
        # balance sheet FY2023 (filed 2024-02-15) and FY2022 (filed 2023-02-15)
        fact("TotalAssets", "2023-12-31", 1000, "2024-02-15"), fact("TotalAssets", "2022-12-31", 900, "2023-02-15"),
        fact("TotalLiabilities", "2023-12-31", 600, "2024-02-15"), fact("TotalLiabilities", "2022-12-31", 500, "2023-02-15"),
        fact("StockholdersEquity", "2023-12-31", 400, "2024-02-15"), fact("StockholdersEquity", "2022-12-31", 400, "2023-02-15"),
        fact("CurrentAssets", "2023-12-31", 300, "2024-02-15"), fact("CurrentAssets", "2022-12-31", 280, "2023-02-15"),
        fact("CurrentLiabilities", "2023-12-31", 200, "2024-02-15"), fact("CurrentLiabilities", "2022-12-31", 140, "2023-02-15"),
        fact("RetainedEarnings", "2023-12-31", 250, "2024-02-15"),
        # annual flows
        fact("Revenue", "2023-12-31", 1200, "2024-02-15", "2023-01-01"), fact("Revenue", "2022-12-31", 1000, "2023-02-15", "2022-01-01"),
        fact("NetIncome", "2023-12-31", 120, "2024-02-15", "2023-01-01"), fact("NetIncome", "2022-12-31", 80, "2023-02-15", "2022-01-01"),
        fact("OperatingIncome", "2023-12-31", 150, "2024-02-15", "2023-01-01"),
        # cumulative operating cash flow reported only year-to-date (3M, 6M, 9M) plus the full year
        fact("OperatingCashFlow", "2023-03-31", 30, "2023-05-01", "2023-01-01"),
        fact("OperatingCashFlow", "2023-06-30", 70, "2023-08-01", "2023-01-01"),
        fact("OperatingCashFlow", "2023-09-30", 100, "2023-11-01", "2023-01-01"),
        fact("OperatingCashFlow", "2023-12-31", 160, "2024-02-15", "2023-01-01"),
    ]
    return pd.DataFrame(rows)


def test_ratios_match_hand_computation(facts):
    f, snap = financial.build(facts, "2024-03-01")
    assert snap.period_end == pd.Timestamp("2023-12-31")
    assert f["net_margin"] == pytest.approx(120 / 1200)
    assert f["current_ratio"] == pytest.approx(300 / 200)
    assert f["liabilities_assets"] == pytest.approx(0.6)
    assert f["revenue_yoy"] == pytest.approx(0.2)
    assert f["d_current_ratio"] == pytest.approx(1.5 - 2.0)
    z2 = 6.56 * (100 / 1000) + 3.26 * (250 / 1000) + 6.72 * (150 / 1000) + 1.05 * (400 / 600)
    assert f["altman_z2"] == pytest.approx(z2)


def test_quarter_derivation_from_cumulative_values(facts):
    view = financial.known_as_of(facts, pd.Timestamp("2024-03-01"))
    q = financial.quarterly_series(view, "OperatingCashFlow")
    assert list(q.round(6)) == [30, 40, 30, 60]  # Q2 = 6M - 3M, Q3 = 9M - 6M, Q4 = FY - 9M


def test_no_lookahead(facts):
    """As of 2024-01-31 the FY2023 10-K (filed 2024-02-15) is not public yet: the snapshot must use FY2022."""
    f, snap = financial.build(facts, "2024-01-31")
    assert snap.period_end == pd.Timestamp("2022-12-31")
    assert f["net_margin"] == pytest.approx(80 / 1000)
    view = financial.known_as_of(facts, pd.Timestamp("2024-01-31"))
    assert (view.fi <= pd.Timestamp("2024-01-31").value).all()


def test_restated_value_is_used_only_after_its_filing(facts):
    restated = pd.concat([facts, pd.DataFrame([fact("NetIncome", "2023-12-31", 60, "2024-06-01", "2023-01-01")])])
    before, _ = financial.build(restated, "2024-03-01")
    after, _ = financial.build(restated, "2024-07-01")
    assert before["net_margin"] == pytest.approx(0.10)
    assert after["net_margin"] == pytest.approx(0.05)


def test_missing_data_is_nan_not_zero():
    f, snap = financial.build(pd.DataFrame([fact("TotalAssets", "2023-12-31", 10, "2024-01-10")]), "2024-02-01")
    assert snap.period_end is not None
    assert np.isnan(f["net_margin"]) and np.isnan(f["altman_z2"])
