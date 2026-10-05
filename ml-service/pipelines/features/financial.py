"""Point-in-time financial feature builder (ML_PIPELINE §5).

`build(facts, as_of)` is the single feature builder used by training (one call per 10-K filing date)
and by inference (one call per analysis date), so the two cannot diverge. Only facts with
`filed <= as_of` are ever read.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

QUARTER_DAYS = (75, 105)
ANNUAL_DAYS = (340, 390)

# Feature names produced by build(); order is the model's column order.
FEATURES = [
    "log_assets", "net_margin", "roa", "ebit_assets", "gross_margin",
    "current_ratio", "cash_assets", "debt_equity", "liabilities_assets", "interest_coverage",
    "negative_equity", "ocf_liabilities", "fcf_margin", "neg_fcf_quarters",
    "revenue_yoy", "d_net_margin", "d_current_ratio", "revenue_slope_8q",
    "wc_ta", "re_ta", "be_tl", "altman_z2", "ohlson_o", "piotroski_f", "beneish_m",
    "float_liabilities", "filing_lag_days",
]


@dataclass
class Snapshot:
    """Resolved values (as known at `as_of`) needed by the feature formulas."""

    period_end: pd.Timestamp | None
    values: dict[str, float]
    prev: dict[str, float]
    quarterly: dict[str, pd.Series]


NAT = np.iinfo(np.int64).min
DAY_NS = 86_400_000_000_000


def _empty_series() -> pd.Series:
    return pd.Series(dtype=float, index=pd.DatetimeIndex([]))


def _ns(col: pd.Series) -> np.ndarray:
    return col.to_numpy(dtype="datetime64[ns]").astype(np.int64)  # NaT -> int64 min


class FactStore:
    """One company's canonical facts, sorted once so point-in-time queries are pure NumPy.

    Sort order: item, period start, period end, tag rank (best first), filed date (latest first).
    """

    def __init__(self, facts: pd.DataFrame):
        if len(facts):  # XBRL occasionally carries typo'd dates (e.g. year 0201); they would overflow ns timestamps
            lo, hi = pd.Timestamp("1990-01-01"), pd.Timestamp("2100-01-01")
            ok = (facts["end"].between(lo, hi) & facts["filed"].between(lo, hi)
                  & (facts["start"].isna() | facts["start"].between(lo, hi)))
            facts = facts[ok]
        self.items = sorted(facts["item"].astype(str).unique()) if len(facts) else []
        codes = {name: i for i, name in enumerate(self.items)}
        ic = facts["item"].astype(str).map(codes).to_numpy(dtype=np.int32) if len(facts) else np.array([], np.int32)
        st, en, fi = (_ns(facts[c]) for c in ("start", "end", "filed")) if len(facts) else (np.array([], np.int64),) * 3
        rk = facts["rank"].to_numpy(dtype=np.int16) if len(facts) else np.array([], np.int16)
        val = facts["val"].to_numpy(dtype=float) if len(facts) else np.array([], float)
        order = np.lexsort((-fi, rk, en, st, ic))
        self.ic, self.st, self.en, self.rk, self.fi, self.val = ic[order], st[order], en[order], rk[order], fi[order], val[order]
        self.codes = codes

    def __len__(self) -> int:
        return len(self.ic)


class FactView:
    """Facts known at one as-of date: one value per (item, start, end)."""

    def __init__(self, store: FactStore, as_of: pd.Timestamp):
        m = store.fi <= np.int64(pd.Timestamp(as_of).value)
        ic, st, en = store.ic[m], store.st[m], store.en[m]
        first = np.ones(len(ic), dtype=bool)
        if len(ic) > 1:
            first[1:] = (ic[1:] != ic[:-1]) | (st[1:] != st[:-1]) | (en[1:] != en[:-1])
        self.ic, self.st, self.en = ic[first], st[first], en[first]
        self.rk, self.fi, self.val = store.rk[m][first], store.fi[m][first], store.val[m][first]
        self.codes = store.codes

    @property
    def empty(self) -> bool:
        return len(self.ic) == 0

    def rows(self, item: str) -> slice:
        code = self.codes.get(item)
        if code is None:
            return slice(0, 0)
        return slice(np.searchsorted(self.ic, code, "left"), np.searchsorted(self.ic, code, "right"))


def _series(ends: np.ndarray, vals: np.ndarray) -> pd.Series:
    if len(ends) == 0:
        return _empty_series()
    return pd.Series(vals, index=pd.DatetimeIndex(ends.astype("datetime64[ns]")), dtype=float)


def known_as_of(facts: pd.DataFrame | FactStore, as_of: pd.Timestamp) -> FactView:
    """Facts public at `as_of`, one value per (item, period): best tag rank, then latest filing."""
    store = facts if isinstance(facts, FactStore) else FactStore(facts)
    return FactView(store, as_of)


def _first_per_end(en: np.ndarray, rk: np.ndarray, val: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    order = np.lexsort((rk, en))
    en, val = en[order], val[order]
    keep = np.ones(len(en), dtype=bool)
    keep[1:] = en[1:] != en[:-1]
    return en[keep], val[keep]


def instant_series(view: FactView, item: str) -> pd.Series:
    sl = view.rows(item)
    return _series(*_first_per_end(view.en[sl], view.rk[sl], view.val[sl]))


def annual_series(view: FactView, item: str) -> pd.Series:
    sl = view.rows(item)
    st, en, rk, val = view.st[sl], view.en[sl], view.rk[sl], view.val[sl]
    has_start = st != NAT
    dur = np.where(has_start, (en - st) // DAY_NS, -1)
    m = (dur >= ANNUAL_DAYS[0]) & (dur <= ANNUAL_DAYS[1])
    return _series(*_first_per_end(en[m], rk[m], val[m]))


def quarterly_series(view: FactView, item: str) -> pd.Series:
    """Discrete quarter values. Quarters that are only reported cumulatively (e.g. 6- and 9-month
    cash flows, or Q4 = FY - 9M) are derived as differences of consecutive cumulative values."""
    sl = view.rows(item)
    st, en, val = view.st[sl], view.en[sl], view.val[sl]
    m = st != NAT
    st, en, val = st[m], en[m], val[m]
    if len(st) == 0:
        return _empty_series()
    dur = (en - st) // DAY_NS
    quarters: dict[int, float] = {}
    for e, v, d in zip(en, val, dur, strict=True):
        if QUARTER_DAYS[0] <= d <= QUARTER_DAYS[1]:
            quarters.setdefault(int(e), float(v))
    # rows are sorted by (start, end): walk each cumulative chain sharing a start date
    for i in range(1, len(st)):
        if st[i] == st[i - 1]:
            gap = (en[i] - en[i - 1]) // DAY_NS
            if QUARTER_DAYS[0] <= gap <= QUARTER_DAYS[1] and int(en[i]) not in quarters:
                quarters[int(en[i])] = float(val[i] - val[i - 1])
    if not quarters:
        return _empty_series()
    ends = np.array(sorted(quarters), dtype=np.int64)
    vals = np.array([quarters[e] for e in ends])
    # Drop near-duplicate quarter ends (52/53-week calendars) keeping the later one.
    if len(ends) > 1:
        keep = np.append(np.diff(ends) // DAY_NS > 20, True)
        ends, vals = ends[keep], vals[keep]
    return _series(ends, vals)


def _latest(s: pd.Series, on_or_before: pd.Timestamp | None = None, max_age_days: int | None = None):
    if on_or_before is not None:
        s = s[s.index <= on_or_before]
    if s.empty:
        return np.nan, None
    end = s.index[-1]
    if on_or_before is not None and max_age_days is not None and (on_or_before - end).days > max_age_days:
        return np.nan, None
    return float(s.iloc[-1]), end


def ttm(quarterly: pd.Series, annual: pd.Series, end_target: pd.Timestamp, tolerance_days: int = 50) -> float:
    """Trailing-twelve-month value for the period ending near `end_target`."""
    a_val, a_end = _latest(annual, end_target + pd.Timedelta(days=tolerance_days))
    if a_end is not None and abs((a_end - end_target).days) <= tolerance_days:
        return a_val
    q = quarterly[quarterly.index <= end_target + pd.Timedelta(days=tolerance_days)]
    if len(q) >= 4 and abs((q.index[-1] - end_target).days) <= tolerance_days:
        span = (q.index[-1] - q.index[-4]).days
        if 240 <= span <= 300:
            return float(q.iloc[-4:].sum())
    return np.nan


FLOW_ITEMS = ["Revenue", "CostOfRevenue", "GrossProfit", "OperatingIncome", "NetIncome", "InterestExpense",
              "SGA", "Depreciation", "OperatingCashFlow", "CapEx"]
STOCK_ITEMS = ["TotalAssets", "CurrentAssets", "CurrentLiabilities", "TotalLiabilities", "StockholdersEquity",
               "LiabilitiesAndEquity", "RetainedEarnings", "Cash", "LongTermDebt", "Inventory", "Receivables",
               "PPE", "SharesOutstanding", "PublicFloat", "Deposits", "Loans", "HtmAmortizedCost", "HtmFairValue",
               "AfsAmortizedCost", "AfsFairValue"]


def snapshot(facts: pd.DataFrame | FactStore, as_of: pd.Timestamp) -> Snapshot:
    """Resolve the latest balance sheet and TTM flows known at `as_of`, plus the same one year earlier."""
    resolved = known_as_of(facts, as_of)
    if resolved.empty:
        return Snapshot(None, {}, {}, {})
    assets = instant_series(resolved, "TotalAssets")
    _, period_end = _latest(assets, as_of)
    if period_end is None:
        return Snapshot(None, {}, {}, {})
    prev_end = period_end - pd.Timedelta(days=365)

    values: dict[str, float] = {}
    prev: dict[str, float] = {}
    for item in STOCK_ITEMS:
        s = instant_series(resolved, item)
        tol = 400 if item == "PublicFloat" else 45  # public float is measured at mid-year
        values[item], _ = _latest(s, period_end + pd.Timedelta(days=5), max_age_days=tol)
        prev[item], _ = _latest(s, prev_end + pd.Timedelta(days=5), max_age_days=tol)
    quarterly: dict[str, pd.Series] = {}
    for item in FLOW_ITEMS:
        q, a = quarterly_series(resolved, item), annual_series(resolved, item)
        quarterly[item] = q
        values[item] = ttm(q, a, period_end)
        prev[item] = ttm(q, a, prev_end)
    for target in (values, prev):
        _fill_derived(target)
    return Snapshot(period_end, values, prev, quarterly)


def _fill_derived(v: dict[str, float]) -> None:
    if np.isnan(v.get("TotalLiabilities", np.nan)):
        le, eq = v.get("LiabilitiesAndEquity", np.nan), v.get("StockholdersEquity", np.nan)
        v["TotalLiabilities"] = le - eq if not (np.isnan(le) or np.isnan(eq)) else np.nan
    if np.isnan(v.get("GrossProfit", np.nan)):
        rev, cogs = v.get("Revenue", np.nan), v.get("CostOfRevenue", np.nan)
        v["GrossProfit"] = rev - cogs if not (np.isnan(rev) or np.isnan(cogs)) else np.nan


def _div(a: float, b: float) -> float:
    if a is None or b is None or np.isnan(a) or np.isnan(b) or b == 0:
        return np.nan
    return a / b


def _theil_sen_slope(y: np.ndarray) -> float:
    y = y[~np.isnan(y)]
    n = len(y)
    if n < 4:
        return np.nan
    slopes = [(y[j] - y[i]) / (j - i) for i in range(n) for j in range(i + 1, n)]
    return float(np.median(slopes))


def piotroski_f(v: dict, p: dict) -> float:
    roa, roa_p = _div(v["NetIncome"], v["TotalAssets"]), _div(p["NetIncome"], p["TotalAssets"])
    if np.isnan(roa):
        return np.nan
    signals = [
        roa > 0,
        v["OperatingCashFlow"] > 0,
        roa > roa_p if not np.isnan(roa_p) else False,
        v["OperatingCashFlow"] > v["NetIncome"],
        _div(v["LongTermDebt"], v["TotalAssets"]) < _div(p["LongTermDebt"], p["TotalAssets"]),
        _div(v["CurrentAssets"], v["CurrentLiabilities"]) > _div(p["CurrentAssets"], p["CurrentLiabilities"]),
        not (v["SharesOutstanding"] > p["SharesOutstanding"] * 1.02),
        _div(v["GrossProfit"], v["Revenue"]) > _div(p["GrossProfit"], p["Revenue"]),
        _div(v["Revenue"], v["TotalAssets"]) > _div(p["Revenue"], p["TotalAssets"]),
    ]
    return float(sum(bool(s) for s in signals))


FORENSIC_FEATURES = ["bn_dsri", "bn_gmi", "bn_aqi", "bn_sgi", "bn_depi", "bn_sgai", "bn_lvgi", "bn_tata"]


def beneish_indices(v: dict, p: dict) -> dict[str, float]:
    """The eight Beneish (1999) indices (inputs of M5b, the financial-statement anomaly model)."""
    rev, rev_p = v["Revenue"], p["Revenue"]
    return {
        "bn_dsri": _div(_div(v["Receivables"], rev), _div(p["Receivables"], rev_p)),
        "bn_gmi": _div(_div(p["GrossProfit"], rev_p), _div(v["GrossProfit"], rev)),
        "bn_aqi": _div(1 - _div(v["CurrentAssets"] + v["PPE"], v["TotalAssets"]),
                       1 - _div(p["CurrentAssets"] + p["PPE"], p["TotalAssets"])),
        "bn_sgi": _div(rev, rev_p),
        "bn_depi": _div(_div(p["Depreciation"], p["Depreciation"] + p["PPE"]),
                        _div(v["Depreciation"], v["Depreciation"] + v["PPE"])),
        "bn_sgai": _div(_div(v["SGA"], rev), _div(p["SGA"], rev_p)),
        "bn_lvgi": _div(_div(v["TotalLiabilities"], v["TotalAssets"]), _div(p["TotalLiabilities"], p["TotalAssets"])),
        "bn_tata": _div(v["NetIncome"] - v["OperatingCashFlow"], v["TotalAssets"]),
    }


def beneish_m(v: dict, p: dict) -> float:
    """Beneish (1999) 8-variable M-score; NaN when any input is missing."""
    rev, rev_p = v["Revenue"], p["Revenue"]
    dsri = _div(_div(v["Receivables"], rev), _div(p["Receivables"], rev_p))
    gmi = _div(_div(p["GrossProfit"], rev_p), _div(v["GrossProfit"], rev))
    aqi = _div(1 - _div(v["CurrentAssets"] + v["PPE"], v["TotalAssets"]),
               1 - _div(p["CurrentAssets"] + p["PPE"], p["TotalAssets"]))
    sgi = _div(rev, rev_p)
    depi = _div(_div(p["Depreciation"], p["Depreciation"] + p["PPE"]), _div(v["Depreciation"], v["Depreciation"] + v["PPE"]))
    sgai = _div(_div(v["SGA"], rev), _div(p["SGA"], rev_p))
    lvgi = _div(_div(v["TotalLiabilities"], v["TotalAssets"]), _div(p["TotalLiabilities"], p["TotalAssets"]))
    tata = _div(v["NetIncome"] - v["OperatingCashFlow"], v["TotalAssets"])
    parts = [dsri, gmi, aqi, sgi, depi, sgai, lvgi, tata]
    if any(np.isnan(x) for x in parts):
        return np.nan
    return (-4.84 + 0.920 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi
            - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)


def compute_features(snap: Snapshot, latest_filing: tuple[pd.Timestamp, pd.Timestamp] | None = None) -> dict:
    """Feature dict (FEATURES order) from a snapshot. NaN means 'not computable from public data'."""
    f = dict.fromkeys(FEATURES + FORENSIC_FEATURES, np.nan)
    if snap.period_end is None:
        return f
    v, p = snap.values, snap.prev
    ta, tl, eq = v["TotalAssets"], v["TotalLiabilities"], v["StockholdersEquity"]
    ebit = v["OperatingIncome"]
    f["log_assets"] = math.log10(ta) if ta and ta > 0 else np.nan
    f["net_margin"] = _div(v["NetIncome"], v["Revenue"])
    f["roa"] = _div(v["NetIncome"], ta)
    f["ebit_assets"] = _div(ebit, ta)
    f["gross_margin"] = _div(v["GrossProfit"], v["Revenue"])
    f["current_ratio"] = _div(v["CurrentAssets"], v["CurrentLiabilities"])
    f["cash_assets"] = _div(v["Cash"], ta)
    f["debt_equity"] = _div(v["LongTermDebt"], eq) if eq and eq > 0 else np.nan
    f["liabilities_assets"] = _div(tl, ta)
    interest = v["InterestExpense"]
    f["interest_coverage"] = _div(ebit, abs(interest)) if interest and abs(interest) > 0 else np.nan
    f["negative_equity"] = float(eq < 0) if not np.isnan(eq) else np.nan
    f["ocf_liabilities"] = _div(v["OperatingCashFlow"], tl)
    f["fcf_margin"] = _div(v["OperatingCashFlow"] - (v["CapEx"] if not np.isnan(v["CapEx"]) else 0.0), v["Revenue"])

    ocf_q, capex_q = snap.quarterly.get("OperatingCashFlow"), snap.quarterly.get("CapEx")
    if ocf_q is not None and len(ocf_q) >= 4:
        last4 = ocf_q.iloc[-4:]
        cap = capex_q.reindex(last4.index).fillna(0.0) if capex_q is not None else 0.0
        f["neg_fcf_quarters"] = float(((last4 - cap) < 0).sum())

    f["revenue_yoy"] = _div(v["Revenue"], p["Revenue"]) - 1 if p["Revenue"] and p["Revenue"] > 0 else np.nan
    f["d_net_margin"] = f["net_margin"] - _div(p["NetIncome"], p["Revenue"])
    f["d_current_ratio"] = f["current_ratio"] - _div(p["CurrentAssets"], p["CurrentLiabilities"])
    rev_q = snap.quarterly.get("Revenue")
    if rev_q is not None and len(rev_q) >= 4:
        last8 = rev_q.iloc[-8:].to_numpy()
        mean = np.nanmean(np.abs(last8))
        f["revenue_slope_8q"] = _theil_sen_slope(last8) / mean if mean else np.nan

    f["wc_ta"] = _div(v["CurrentAssets"] - v["CurrentLiabilities"], ta)
    f["re_ta"] = _div(v["RetainedEarnings"], ta)
    f["be_tl"] = _div(eq, tl)
    if not any(np.isnan(x) for x in (f["wc_ta"], f["re_ta"], f["ebit_assets"], f["be_tl"])):
        f["altman_z2"] = 6.56 * f["wc_ta"] + 3.26 * f["re_ta"] + 6.72 * f["ebit_assets"] + 1.05 * f["be_tl"]

    ni, ni_p = v["NetIncome"], p["NetIncome"]
    if not any(np.isnan(x) for x in (ta, tl, v["CurrentAssets"], v["CurrentLiabilities"], ni)) and ta > 0:
        size = math.log(ta / 1e6)
        oeneg = float(tl > ta)
        futl = _div(v["OperatingCashFlow"], tl)
        intwo = float(ni < 0 and (ni_p < 0 if not np.isnan(ni_p) else False))
        chin = (ni - ni_p) / (abs(ni) + abs(ni_p)) if not np.isnan(ni_p) and (abs(ni) + abs(ni_p)) > 0 else 0.0
        f["ohlson_o"] = (-1.32 - 0.407 * size + 6.03 * _div(tl, ta) - 1.43 * f["wc_ta"]
                         + 0.0757 * _div(v["CurrentLiabilities"], v["CurrentAssets"]) - 1.72 * oeneg
                         - 2.37 * _div(ni, ta) - 1.83 * (futl if not np.isnan(futl) else 0.0)
                         + 0.285 * intwo - 0.521 * chin)
    f["piotroski_f"] = piotroski_f(v, p)
    f["beneish_m"] = beneish_m(v, p)
    f.update(beneish_indices(v, p))
    f["float_liabilities"] = _div(v["PublicFloat"], tl)
    if latest_filing is not None:
        period, filed = latest_filing
        f["filing_lag_days"] = float((filed - period).days)
    return f


def build(facts: pd.DataFrame | FactStore, as_of: pd.Timestamp | str,
          latest_filing: tuple[pd.Timestamp, pd.Timestamp] | None = None) -> tuple[dict, Snapshot]:
    as_of = pd.Timestamp(as_of)
    snap = snapshot(facts, as_of)
    return compute_features(snap, latest_filing), snap
