"""Health-score engine (SCORING.md): factors -> pillars -> composite, confidence, caps, attribution, signals.

Everything here is a documented statistical calculation (Kind = Stat) or a deterministic rule (Rule);
ML outputs (sentiment, anomaly, distress) enter as inputs and keep their own Kind tag.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.inference.peers import PeerStats
from app.schemas.analysis import Factor, Health, Pillar, Signal

PILLAR_WEIGHTS = {"financial": 0.30, "market": 0.20, "news": 0.20, "workforce": 0.15, "events": 0.15}
PILLAR_LABELS = {"financial": "Financial stability", "market": "Market behaviour", "news": "News sentiment",
                 "workforce": "Workforce", "events": "Events & governance"}
BANDS = [(70, "STRONG"), (55, "STABLE"), (40, "WATCH"), (25, "WEAK"), (0, "CRITICAL")]
MIN_CONFIDENCE = 0.40
EVENT_DECAY_DAYS = 180.0
NEWS_PRIOR_WEIGHT = 5.0      # neutral pseudo-headlines in the news-sentiment shrinkage
NEWS_FULL_COVERAGE = 30      # headlines needed for full News-pillar coverage


@dataclass(frozen=True)
class FactorSpec:
    key: str
    label: str
    weight: float
    higher_is_better: bool
    fmt: str = "{:.2f}"


FINANCIAL_FACTORS = [
    FactorSpec("altman_z2", "Altman Z''-score", 0.20, True),
    FactorSpec("piotroski_f", "Piotroski F-score", 0.15, True, "{:.0f}/9"),
    FactorSpec("revenue_yoy", "Revenue growth (YoY, TTM)", 0.15, True, "pct"),
    FactorSpec("net_margin", "Net margin (TTM)", 0.15, True, "pct"),
    FactorSpec("current_ratio", "Current ratio", 0.10, True, "{:.2f}x"),
    FactorSpec("debt_equity", "Long-term debt / equity", 0.10, False, "{:.2f}x"),
    FactorSpec("fcf_margin", "Free-cash-flow margin (TTM)", 0.15, True, "pct"),
]
BANK_FACTORS = [
    FactorSpec("equity_assets", "Equity / total assets", 0.25, True, "pct"),
    FactorSpec("securities_loss_equity", "Unrealised securities loss / equity", 0.25, False, "pct"),
    FactorSpec("deposit_growth", "Deposit growth (YoY)", 0.15, True, "pct"),
    FactorSpec("loans_deposits", "Loans / deposits", 0.10, False, "{:.2f}x"),
    FactorSpec("bank_roa", "Return on assets (TTM)", 0.15, True, "pct"),
]


def fmt_value(value: float | None, fmt: str) -> str | None:
    if value is None or not np.isfinite(value):
        return None
    if fmt == "pct":
        return f"{value * 100:.1f}%"
    return fmt.format(value)


def band_for(score: float | None) -> str:
    if score is None:
        return "INSUFFICIENT_DATA"
    return next(b for threshold, b in BANDS if score >= threshold)


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return float(min(hi, max(lo, x)))


# ------------------------------------------------------------------ inputs
@dataclass
class ScoringInputs:
    as_of: date
    sector: str
    is_bank: bool
    features: dict[str, float]
    peer_table: dict
    peer_table_date: str | None
    financial_freshness: float
    financial_evidence: list[str]
    events: list[dict]                  # canonical events (8-K, forms, news, anomalies), each with date/penalty
    news: pd.DataFrame | None           # columns: published_at, polarity, label, title, evidence_id
    market: dict | None                 # return_6m, return_12m, excess_6m, excess_12m, vol_90d, drawdown_52w
    employee: dict | None               # index, trend, quarter, freshness
    market_anomaly_max: float | None = None
    financial_anomaly: float | None = None
    distress_band: str | None = None
    distress_probability: float | None = None
    notes: dict[str, str] = field(default_factory=dict)


# ------------------------------------------------------------------ factors
def financial_factors(inp: ScoringInputs) -> list[Factor]:
    specs = BANK_FACTORS if inp.is_bank else FINANCIAL_FACTORS
    groups = (["BANKS"] if inp.is_bank else [inp.sector]) + ["ALL"]
    factors = []
    for spec in specs:
        value = inp.features.get(spec.key)
        value = None if value is None or (isinstance(value, float) and math.isnan(value)) else float(value)
        pct, group, n = PeerStats.percentile(inp.peer_table, spec.key, value, groups)
        note = None
        score = None
        if pct is not None:
            score = 100 * pct if spec.higher_is_better else 100 * (1 - pct)
        if spec.key == "piotroski_f" and value is not None:
            score = value / 9 * 100  # absolute scale by definition of the F-score
        if spec.key == "altman_z2" and value is not None and value < 1.1:
            score, note = min(score if score is not None else 20, 20), "distress zone (Z'' < 1.1): capped at 20"
        if spec.key == "current_ratio" and value is not None and value < 1.0:
            score, note = min(score if score is not None else 30, 30), "below 1.0: capped at 30"
        if spec.key == "debt_equity" and inp.features.get("negative_equity") == 1.0:
            score, note = 0.0, "negative shareholders' equity"
        if spec.key == "securities_loss_equity" and value is not None and value > 0.5:
            score, note = min(score if score is not None else 15, 15), "unrealised losses exceed 50% of equity: capped at 15"
        if spec.key == "deposit_growth" and value is not None and value < -0.10:
            score, note = min(score if score is not None else 30, 30), "deposits fell more than 10%: capped at 30"
        factors.append(Factor(
            key=spec.key, label=spec.label, kind="Stat", value=value, display_value=fmt_value(value, spec.fmt),
            score=None if score is None else round(score, 2), peer_percentile=None if pct is None else round(pct, 4),
            peer_group=f"{group} (n={n})" if group else None, weight=spec.weight,
            direction="higher_is_better" if spec.higher_is_better else "lower_is_better",
            note=note or (None if score is not None else "not computable from filed data"),
            evidence=inp.financial_evidence))
    return factors


def market_factors(inp: ScoringInputs) -> list[Factor]:
    m = inp.market or {}
    out = []

    def add(key, label, weight, value, score, higher, fmt, note):
        out.append(Factor(key=key, label=label, kind="Stat", value=value, display_value=fmt_value(value, fmt),
                          score=None if score is None else round(score, 2), weight=weight,
                          direction="higher_is_better" if higher else "lower_is_better", note=note,
                          evidence=["ev:prices"]))
    # Absolute mappings: peer price data is not available for every sector, so no percentiles here.
    ex6 = m.get("excess_6m", m.get("return_6m"))
    ex12 = m.get("excess_12m", m.get("return_12m"))
    rel = "vs sector ETF" if "excess_6m" in m else "absolute (sector ETF unavailable)"
    add("excess_return_6m", f"6-month return {rel}", 0.30, ex6,
        None if ex6 is None else 100 / (1 + math.exp(-ex6 / 0.15)), True, "pct", "logistic map: 0% -> 50, +/-30% -> 88/12")
    add("excess_return_12m", f"12-month return {rel}", 0.20, ex12,
        None if ex12 is None else 100 / (1 + math.exp(-ex12 / 0.20)), True, "pct", "logistic map: 0% -> 50")
    vol = m.get("vol_90d")
    add("volatility_90d", "90-day realised volatility (annualised)", 0.25, vol,
        None if vol is None else _clip((0.80 - vol) / (0.80 - 0.15) * 100), False, "pct", "15% -> 100, 80% -> 0")
    dd = m.get("drawdown_52w")
    add("drawdown_52w", "Drawdown from 52-week high", 0.25, dd,
        None if dd is None else _clip((1 - dd / 0.6) * 100), False, "pct", "0% -> 100, 60% -> 0")
    return out


def news_factors(inp: ScoringInputs) -> list[Factor]:
    df = inp.news
    if df is None or len(df) < 5:
        return []
    as_of = pd.Timestamp(inp.as_of, tz="UTC") + pd.Timedelta(days=1)
    age = (as_of - df["published_at"]).dt.total_seconds() / 86400
    w = np.power(0.5, age / 14.0)
    # Shrink toward neutral with a prior worth NEWS_PRIOR_WEIGHT neutral headlines, so a handful of articles
    # cannot swing the pillar (empirical-Bayes style shrinkage; the prior's weight is a documented parameter).
    level = float(np.sum(w * df["polarity"]) / (np.sum(w) + NEWS_PRIOR_WEIGHT))
    recent, prior = df[age <= 30], df[(age > 30) & (age <= 90)]
    trend = float(recent["polarity"].mean() - prior["polarity"].mean()) if len(recent) >= 3 and len(prior) >= 3 else None
    neg_share = float(((df["label"] == "negative") & (df["polarity"] <= -0.5)).mean())
    ev = ["ev:news"]
    return [
        Factor(key="news_sentiment_level", label="Recency-weighted news sentiment (90 days)", kind="ML",
               value=round(level, 4), display_value=f"{level:+.2f}", score=round(_clip(50 * (1 + level)), 2), weight=0.60,
               note=f"half-life 14 days, shrunk toward 0 by {NEWS_PRIOR_WEIGHT:g} pseudo-headlines; -1..+1 mapped to 0..100",
               evidence=ev),
        Factor(key="news_sentiment_trend", label="Sentiment trend (last 30d vs prior 60d)", kind="ML",
               value=None if trend is None else round(trend, 4),
               display_value=None if trend is None else f"{trend:+.2f}",
               score=None if trend is None else round(_clip(50 + 100 * trend), 2), weight=0.25, evidence=ev,
               note=None if trend is not None else "too few articles in one of the windows"),
        Factor(key="negative_story_share", label="Share of strongly negative stories", kind="ML",
               value=round(neg_share, 4), display_value=f"{neg_share * 100:.1f}%",
               score=round(_clip(100 * (1 - 2 * neg_share)), 2), weight=0.15, direction="lower_is_better", evidence=ev),
    ]


def workforce_factors(inp: ScoringInputs) -> list[Factor]:
    """Needs a level signal (Employee Sentiment Index). Without it the pillar is unavailable rather than scoring
    "no layoffs" as 100; restructuring filings are still penalised in the Events pillar."""
    out = []
    emp = inp.employee
    if not emp:
        return out
    if emp:
        out.append(Factor(key="employee_sentiment", label=f"Employee Sentiment Index ({emp['quarter']})", kind="ML",
                          value=emp["index"], display_value=f"{emp['index']:+.2f}",
                          score=round(_clip(50 * (1 + emp["index"])), 2), weight=0.30, evidence=["ev:reviews"],
                          note="historical dataset; down-weighted by freshness" if emp.get("freshness", 1) < 1 else None))
        if emp.get("trend") is not None:
            out.append(Factor(key="employee_sentiment_trend", label="Employee sentiment trend (4 quarters)", kind="Stat",
                              value=emp["trend"], display_value=f"{emp['trend']:+.3f}/q",
                              score=round(_clip(50 + 400 * emp["trend"]), 2), weight=0.15, evidence=["ev:reviews"]))
    layoffs = [e for e in inp.events if e["type"] in ("RESTRUCTURING", "LAYOFFS")
               and 0 <= (inp.as_of - e["date"]).days <= 365]
    decayed = sum(math.exp(-(inp.as_of - e["date"]).days / EVENT_DECAY_DAYS) for e in layoffs)
    out.append(Factor(key="layoff_events_12m", label="Layoff / restructuring events (12 months, decayed)", kind="Rule",
                      value=round(decayed, 3), display_value=f"{len(layoffs)} event(s)",
                      score=round(_clip(100 - 30 * decayed), 2), weight=0.30, direction="penalty",
                      evidence=[eid for e in layoffs for eid in e["evidence"]][:6]))
    return out


def events_factor(inp: ScoringInputs) -> tuple[list[Factor], list[dict]]:
    contributing = []
    total = 0.0
    for e in inp.events:
        age = (inp.as_of - e["date"]).days
        if age < 0 or age > 365 or not e.get("penalty"):
            continue
        p = e["penalty"] * math.exp(-age / EVENT_DECAY_DAYS)
        total += p
        contributing.append({**e, "decayed_penalty": round(p, 2)})
    score = _clip(100 - total)
    contributing.sort(key=lambda e: -e["decayed_penalty"])
    note = "; ".join(f"{e['label']} ({e['date']}): -{e['decayed_penalty']:.1f}" for e in contributing[:4]) or \
        "no material adverse events in the last 12 months"
    return [Factor(key="material_events", label="Material-event penalty (12 months, decayed)", kind="Rule",
                   value=round(total, 2), display_value=f"-{total:.1f} pts", score=round(score, 2), weight=1.0,
                   direction="penalty", note=note,
                   evidence=[eid for e in contributing for eid in e["evidence"]][:8])], contributing


# ------------------------------------------------------------------ composite
def build_pillar(key: str, factors: list[Factor], freshness: float, reason: str | None) -> Pillar:
    total_w = sum(f.weight for f in factors) or 1.0
    avail = [f for f in factors if f.score is not None]
    avail_w = sum(f.weight for f in avail)
    coverage = (avail_w / total_w if factors else 0.0) * freshness
    score = sum(f.weight * f.score for f in avail) / avail_w if avail_w else None
    return Pillar(key=key, label=PILLAR_LABELS[key], score=None if score is None else round(score, 2),
                  weight=PILLAR_WEIGHTS[key], effective_weight=0.0, coverage=round(coverage, 4),
                  unavailable_reason=None if score is not None else (reason or "no data"), factors=factors)


def composite(pillars: list[Pillar], caps: list[tuple[float, str]]) -> Health:
    available = [p for p in pillars if p.score is not None]
    confidence = sum(p.weight * p.coverage for p in pillars)
    w_sum = sum(p.weight for p in available)
    for p in pillars:
        p.effective_weight = round(p.weight / w_sum, 4) if p.score is not None and w_sum else 0.0
        if p.score is None:
            continue
        a_sum = sum(f.weight for f in p.factors if f.score is not None)
        for f in p.factors:  # exact additive attribution (SCORING §4)
            f.impact = round(p.effective_weight * (f.weight / a_sum) * (f.score - 50), 4) if f.score is not None else 0.0
    raw = sum(p.effective_weight * p.score for p in available) if available else None
    if raw is None or confidence < MIN_CONFIDENCE:
        return Health(score=None, band="INSUFFICIENT_DATA", confidence=round(confidence, 3),
                      raw_score=None if raw is None else round(raw, 2),
                      override="confidence below 0.40: too little public data for a reliable score")
    final, override = raw, None
    for cap, reason in caps:
        if final > cap:
            final, override = cap, f"capped at {cap:.0f}: {reason}"
    score = int(round(final))
    return Health(score=score, band=band_for(score), confidence=round(confidence, 3), raw_score=round(raw, 2),
                  override=override)


def score_company(inp: ScoringInputs, unavailable: dict[str, str]) -> tuple[Health, list[Pillar], list[dict]]:
    fin = build_pillar("financial", financial_factors(inp), inp.financial_freshness, unavailable.get("financial"))
    mkt = build_pillar("market", market_factors(inp) if inp.market else [], 1.0, unavailable.get("market"))
    n_articles = 0 if inp.news is None else len(inp.news)
    nws = build_pillar("news", news_factors(inp), min(1.0, n_articles / NEWS_FULL_COVERAGE),
                       unavailable.get("news") or "fewer than 5 relevant headlines")
    emp_fresh = inp.employee.get("freshness", 1.0) if inp.employee else 1.0
    wf_factors = workforce_factors(inp)
    wf = build_pillar("workforce", wf_factors, 1.0, unavailable.get("workforce"))
    if inp.employee:
        # Coverage = share of the pillar's full factor weight (incl. the job-board factor, 0.25) that is available,
        # with the review-based factors scaled by the freshness of the review data.
        review_w = sum(f.weight for f in wf_factors if f.key.startswith("employee"))
        other_w = sum(f.weight for f in wf_factors if not f.key.startswith("employee"))
        wf.coverage = round(other_w + review_w * emp_fresh, 4)
    ev_factors, contributing = events_factor(inp)
    evt = build_pillar("events", ev_factors, 1.0, None)
    pillars = [fin, mkt, nws, wf, evt]
    caps = []
    for e in contributing:
        if e.get("cap") is not None:
            caps.append((float(e["cap"]), f"{e['label']} on {e['date']}"))
    caps.sort()
    return composite(pillars, caps), pillars, contributing


# ------------------------------------------------------------------ signals
def warning_signals(inp: ScoringInputs, news_daily: pd.Series | None) -> list[Signal]:
    s: list[Signal] = []
    f = inp.features

    def recent(types: tuple[str, ...], days: int) -> list[dict]:
        return [e for e in inp.events if e["type"] in types and 0 <= (inp.as_of - e["date"]).days <= days]

    rules = [
        ("BANKRUPTCY", ("BANKRUPTCY",), 365, "CRITICAL", "Bankruptcy or receivership disclosed (8-K Item 1.03)"),
        ("RESTATEMENT", ("RESTATEMENT",), 365, "HIGH", "Non-reliance on previously issued financial statements (8-K Item 4.02)"),
        ("DELISTING", ("DELISTING_NOTICE",), 365, "HIGH", "Exchange delisting notice / listing-rule failure (8-K Item 3.01)"),
        ("LATE_FILING", ("LATE_FILING",), 365, "HIGH", "Notification of late filing (NT 10-K / NT 10-Q)"),
        ("DEBT_ACCELERATION", ("DEBT_ACCELERATION",), 365, "HIGH", "Event accelerating a financial obligation (8-K Item 2.04)"),
        ("AUDITOR_CHANGE", ("AUDITOR_CHANGE",), 365, "MEDIUM", "Change of certifying accountant (8-K Item 4.01)"),
        ("LAYOFFS", ("RESTRUCTURING", "LAYOFFS"), 90, "MEDIUM", "Layoffs or restructuring disclosed in the last 90 days"),
        ("CYBER_INCIDENT", ("CYBER_INCIDENT",), 365, "MEDIUM", "Material cybersecurity incident disclosed"),
    ]
    for code, types, days, severity, message in rules:
        hits = recent(types, days)
        if hits:
            latest = max(hits, key=lambda e: e["date"])
            s.append(Signal(code=code, severity=severity, kind="Rule", date=latest["date"], message=message,
                            evidence=[eid for e in hits for eid in e["evidence"]][:5]))
    departures = recent(("EXEC_DEPARTURE",), 180)
    if len(departures) >= 3:
        s.append(Signal(code="EXEC_TURNOVER", severity="MEDIUM", kind="Rule", date=max(e["date"] for e in departures),
                        message=f"{len(departures)} director/officer change filings (8-K Item 5.02) in 180 days",
                        evidence=[eid for e in departures for eid in e["evidence"]][:5]))
    z2 = f.get("altman_z2")
    if not inp.is_bank and z2 is not None and np.isfinite(z2) and z2 < 1.1:
        s.append(Signal(code="ALTMAN_DISTRESS", severity="HIGH", kind="Stat",
                        message=f"Altman Z''-score {z2:.2f} is in the distress zone (< 1.1)", evidence=inp.financial_evidence))
    cr, negq = f.get("current_ratio"), f.get("neg_fcf_quarters")
    if cr is not None and np.isfinite(cr) and cr < 1.0 and negq is not None and np.isfinite(negq) and negq >= 2:
        s.append(Signal(code="LIQUIDITY_SQUEEZE", severity="HIGH", kind="Stat",
                        message=f"Current ratio {cr:.2f} with negative free cash flow in {int(negq)} of the last 4 quarters",
                        evidence=inp.financial_evidence))
    if f.get("negative_equity") == 1.0:
        s.append(Signal(code="NEGATIVE_EQUITY", severity="MEDIUM", kind="Stat",
                        message="Total liabilities exceed total assets (negative shareholders' equity)",
                        evidence=inp.financial_evidence))
    if inp.is_bank:
        loss = f.get("securities_loss_equity")
        if loss is not None and np.isfinite(loss) and loss > 0.5:
            s.append(Signal(code="SECURITIES_LOSSES", severity="HIGH", kind="Stat",
                            message=f"Unrealised securities losses equal {loss * 100:.0f}% of equity", evidence=inp.financial_evidence))
        dep = f.get("deposit_growth")
        if dep is not None and np.isfinite(dep) and dep < -0.10:
            s.append(Signal(code="DEPOSIT_OUTFLOW", severity="HIGH", kind="Stat",
                            message=f"Deposits fell {abs(dep) * 100:.0f}% year over year", evidence=inp.financial_evidence))
    if inp.market and inp.market.get("drawdown_52w") is not None and inp.market["drawdown_52w"] >= 0.30:
        s.append(Signal(code="DRAWDOWN", severity="MEDIUM", kind="Stat",
                        message=f"Share price {inp.market['drawdown_52w'] * 100:.0f}% below its 52-week high", evidence=["ev:prices"]))
    if inp.market_anomaly_max is not None and inp.market_anomaly_max >= 0.99:
        s.append(Signal(code="MARKET_ANOMALY", severity="LOW", kind="ML",
                        message="Unusual trading pattern in the last 14 days (market anomaly detector)", evidence=["ev:prices"]))
    if inp.financial_anomaly is not None and inp.financial_anomaly >= 0.95:
        s.append(Signal(code="STATEMENT_ANOMALY", severity="MEDIUM", kind="ML",
                        message="Year-over-year changes in the latest statements are unusual (top 5% anomaly score)",
                        evidence=inp.financial_evidence))
    if inp.distress_band in ("HIGH", "ELEVATED"):
        s.append(Signal(code="DISTRESS_MODEL", severity="HIGH" if inp.distress_band == "HIGH" else "MEDIUM", kind="ML",
                        message=f"Distress model estimates a {inp.distress_probability * 100:.1f}% probability of a "
                                f"bankruptcy filing within 12 months ({inp.distress_band.lower()} band)",
                        evidence=inp.financial_evidence))
    if news_daily is not None and len(news_daily) >= 20:
        last7 = news_daily[news_daily.index > news_daily.index.max() - pd.Timedelta(days=7)]
        base = news_daily[news_daily.index <= news_daily.index.max() - pd.Timedelta(days=7)]
        if len(base) >= 10 and inp.news is not None:
            n7 = int((inp.news["published_at"] > inp.news["published_at"].max() - pd.Timedelta(days=7)).sum())
            if n7 >= 5 and last7.mean() < base.mean() - 2 * base.std():
                s.append(Signal(code="SENTIMENT_SHOCK", severity="MEDIUM", kind="ML",
                                message="News sentiment in the last 7 days is more than 2 standard deviations below its 90-day baseline",
                                evidence=["ev:news"]))
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    return sorted(s, key=lambda x: (order[x.severity], -(x.date or date.min).toordinal()))


def market_metrics(daily: pd.DataFrame | None, weekly: pd.DataFrame | None, etf_weekly: pd.DataFrame | None,
                   as_of: date) -> dict | None:
    """Market factors as of a date. Returns/drawdown/excess use the weekly split- and dividend-adjusted series
    (full history on the free data tier); volatility uses the last 63 trading days when daily data covers the
    date, otherwise 13 weekly returns. Falls back to a long daily series (e.g. a user-supplied CSV)."""
    t = pd.Timestamp(as_of)

    def ret(series: pd.Series, n: int) -> float | None:
        return float(series.iloc[-1] / series.iloc[-n - 1] - 1) if len(series) > n else None

    d = daily[daily.index <= t]["close"] if daily is not None else pd.Series(dtype=float)
    daily_ok = len(d) >= 63 and (t - d.index[-1]).days <= 10
    w = weekly[weekly.index <= t]["close"] if weekly is not None else pd.Series(dtype=float)
    if len(w) >= 53 and (t - w.index[-1]).days <= 10:
        series, per_year, basis = w, 52, "weekly adjusted close"
    elif len(d) >= 253 and daily_ok:
        series, per_year, basis = d, 252, "daily close (split-adjusted)"
    else:
        return None
    n6, n12 = per_year // 2, per_year
    vol = (float(np.log(d).diff().iloc[-63:].std() * np.sqrt(252)) if daily_ok
           else float(np.log(series).diff().iloc[-13 if per_year == 52 else -63:].std() * np.sqrt(per_year)))
    out = {"return_6m": ret(series, n6), "return_12m": ret(series, n12), "vol_90d": vol,
           "drawdown_52w": float(1 - series.iloc[-1] / series.iloc[-(n12 + 1):].max()),
           "last_close": float(series.iloc[-1]), "last_date": series.index[-1].date().isoformat(), "basis": basis}
    if etf_weekly is not None and per_year == 52:
        e = etf_weekly[etf_weekly.index <= t]["close"]
        if len(e) > 52 and (t - e.index[-1]).days <= 10:
            for n, key in ((26, "6m"), (52, "12m")):
                r, re_ = ret(series, n), ret(e, n)
                if r is not None and re_ is not None:
                    out[f"excess_{key}"] = r - re_
    return {k: v for k, v in out.items() if v is not None}


def freshness_for_filing(as_of: date, period_end: date | None) -> float:
    if period_end is None:
        return 0.0
    months = (as_of - period_end).days / 30.4
    return 1.0 if months <= 15 else 0.5 if months <= 24 else 0.25


def daily_sentiment(news: pd.DataFrame) -> pd.Series:
    d = news.assign(day=news["published_at"].dt.tz_convert(None).dt.normalize())
    return d.groupby("day")["polarity"].mean()


def employee_freshness(quarter_end: date, as_of: date) -> float:
    years = (as_of - quarter_end).days / 365.25
    return float(max(0.2, min(1.0, 1.0 - 0.2 * max(0.0, years - 1))))


def days_ago(as_of: date, n: int) -> date:
    return as_of - timedelta(days=n)
