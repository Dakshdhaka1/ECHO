"""Analysis orchestrator: providers -> features -> models -> score -> signals -> explanation (ARCHITECTURE §5)."""

from __future__ import annotations

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd

from app import __version__
from app.adapters.base import CompanyRef, SourceResult
from app.adapters.news import GdeltNewsSource
from app.adapters.prices import BENCHMARK, SECTOR_ETF, PriceRouter
from app.adapters.reviews import CsvReviewSource
from app.adapters.sec import UsSecProvider, filing_url
from app.inference.anomaly import market_feature_frame
from app.inference.explain import explain
from app.inference.news_events import classify
from app.inference.peers import PeerStats
from app.inference.registry import ModelRegistry
from app.inference.scoring import (
    ScoringInputs,
    daily_sentiment,
    employee_freshness,
    freshness_for_filing,
    market_metrics,
    score_company,
    warning_signals,
)
from app.inference.segments import SEGMENT_DESCRIPTIONS
from app.inference.tabular import risk_band
from app.schemas.analysis import (
    AnalysisResult,
    Anomaly,
    CaseStudy,
    CompanyInfo,
    Distress,
    Driver,
    EmployeeSentiment,
    Event,
    EvidenceItem,
    Forecast,
    ForecastPoint,
    NewsSummary,
    Segment,
    SourceStatus,
    Summary,
)
from pipelines.common import is_bank_sic, is_financial_sic, load_mapping, sector_for_sic
from pipelines.features import financial
from pipelines.features.bank import bank_features
from pipelines.features.events import canonical_events
from pipelines.features.financial import FEATURES as FIN_FEATURES
from pipelines.features.financial import known_as_of, quarterly_series

log = logging.getLogger(__name__)

FEATURE_LABELS = {
    "log_assets": "Company size (log total assets)", "net_margin": "Net margin", "roa": "Return on assets",
    "ebit_assets": "Operating income / assets", "gross_margin": "Gross margin", "current_ratio": "Current ratio",
    "cash_assets": "Cash / assets", "debt_equity": "Long-term debt / equity", "liabilities_assets": "Liabilities / assets",
    "interest_coverage": "Interest coverage", "negative_equity": "Negative equity", "ocf_liabilities": "Operating cash flow / liabilities",
    "fcf_margin": "Free-cash-flow margin", "neg_fcf_quarters": "Quarters of negative free cash flow",
    "revenue_yoy": "Revenue growth (YoY)", "d_net_margin": "Change in net margin", "d_current_ratio": "Change in current ratio",
    "revenue_slope_8q": "Revenue trend (8 quarters)", "wc_ta": "Working capital / assets", "re_ta": "Retained earnings / assets",
    "be_tl": "Book equity / liabilities", "altman_z2": "Altman Z''-score", "ohlson_o": "Ohlson O-score",
    "piotroski_f": "Piotroski F-score", "beneish_m": "Beneish M-score", "float_liabilities": "Public float / liabilities",
    "filing_lag_days": "Days from period end to filing", "ev_restatement": "Recent restatement filing",
    "ev_auditor_change": "Recent auditor change", "ev_exec_departure": "Recent officer/director changes",
    "ev_restructuring": "Recent restructuring", "ev_impairment": "Recent impairment", "ev_delisting_notice": "Delisting notice",
    "ev_debt_acceleration": "Debt acceleration event", "ev_late_filing": "Late filing notices", "ev_cyber_incident": "Cyber incident",
    "bn_dsri": "Receivables vs sales index", "bn_gmi": "Gross margin index", "bn_aqi": "Asset quality index",
    "bn_sgi": "Sales growth index", "bn_depi": "Depreciation index", "bn_sgai": "SG&A index", "bn_lvgi": "Leverage index",
    "bn_tata": "Accruals / assets",
}
DISTRESS_BASE_RATE_DEFAULT = None


@dataclass
class Services:
    sec: UsSecProvider
    news: GdeltNewsSource
    prices: PriceRouter
    reviews: CsvReviewSource
    registry: ModelRegistry
    peers: PeerStats
    explanation_provider: str
    anthropic_api_key: str
    llm_model: str
    demo_mode: bool


def _ev_id(prefix: str, key: str) -> str:
    return f"ev:{prefix}-{hashlib.sha1(key.encode()).hexdigest()[:10]}"


def _nan_to_none(v):
    return None if v is None or (isinstance(v, float) and not np.isfinite(v)) else v


class Analyzer:
    def __init__(self, services: Services):
        self.s = services
        self._employee_cache: dict[tuple, tuple] = {}

    # ------------------------------------------------------------------ public
    def analyze(self, ref: CompanyRef, as_of: date | None = None, include_backfill: bool = True) -> AnalysisResult:
        profile = self.s.sec.company_profile(ref)
        if not profile.available:
            raise LookupError(profile.unavailable_reason)
        meta, filings = profile.data
        entry = self.s.sec.universe_entry(meta["cik"])
        recorded_on = profile.retrieved_at.date() if profile.retrieved_at else date.today()
        as_of = as_of or (recorded_on if self.s.demo_mode else date.today())
        ref = CompanyRef(ref.market, f"{int(meta['cik']):010d}", ref.ticker or (meta["tickers"] or [None])[0], meta["name"])
        if entry and not ref.ticker:
            ref = CompanyRef(ref.market, ref.market_id, entry.get("ticker"), meta["name"])
        sic = meta.get("sic")
        sector = sector_for_sic(sic)
        bank = is_bank_sic(sic)
        # Demo-universe companies keep their familiar name (e.g. Bed Bath & Beyond) even if EDGAR now lists the
        # post-bankruptcy shell name; the current legal name is reported separately.
        display_name = entry["name"] if entry else meta["name"]
        company = CompanyInfo(market=ref.market, market_id=ref.market_id, name=display_name, legal_name=meta["name"],
                              ticker=ref.ticker,
                              exchange=(meta.get("exchanges") or [None])[0], sic=sic, sic_description=meta.get("sic_description"),
                              sector=sector, is_bank=bank, former_names=[f["name"] for f in meta.get("former_names", [])],
                              fiscal_year_end=meta.get("fiscal_year_end"))
        case_study = None
        if entry and entry.get("role") == "historical_distress":
            case_study = CaseStudy(as_of=as_of, note=entry.get("case_study", ""))
        as_of_ts = pd.Timestamp(as_of) + pd.Timedelta(hours=23, minutes=59)
        filings = filings[filings["filed"] <= as_of_ts]

        evidence: dict[str, EvidenceItem] = {}
        sources = [SourceStatus(source="sec_submissions", available=True, retrieved_at=profile.retrieved_at.isoformat(),
                                replayed=self.s.sec.mode == "replay")]
        unavailable: dict[str, str] = {}

        # fetch the slow, independent sources concurrently
        with ThreadPoolExecutor(4) as pool:
            f_facts = pool.submit(self.s.sec.financial_facts, ref)
            f_news = pool.submit(self.s.news.articles, ref, datetime.combine(as_of, datetime.max.time(), UTC), 90,
                                 entry.get("news_query") if entry else None)
            f_prices = pool.submit(self.s.prices.daily, ref.ticker)
            f_weekly = pool.submit(self.s.prices.weekly, ref.ticker)
            f_etf = pool.submit(self.s.prices.weekly, SECTOR_ETF.get(sector, BENCHMARK))
            facts_res, news_res = f_facts.result(), f_news.result()
            price_res, weekly_res, etf_res = f_prices.result(), f_weekly.result(), f_etf.result()

        # ---- financial features
        features: dict[str, float] = {}
        snap = None
        fin_evidence: list[str] = []
        facts = pd.DataFrame()
        store = None
        if facts_res.available:
            facts = facts_res.data
            store = financial.FactStore(facts)
            periodic = filings[filings["form"].str.match(r"^10-[KQ]")]
            latest = periodic.iloc[-1] if len(periodic) else None
            lf = (latest["report_date"], latest["filed"]) if latest is not None and pd.notna(latest["report_date"]) else None
            features, snap = financial.build(store, as_of_ts, latest_filing=lf)
            if bank:
                features.update(bank_features(snap))
            if latest is not None:
                eid = _ev_id("filing", latest["accn"])
                evidence[eid] = EvidenceItem(type="filing", title=f"Form {latest['form']} for period ending "
                                             f"{latest['report_date'].date() if pd.notna(latest['report_date']) else 'n/a'}",
                                             url=filing_url(int(meta["cik"]), latest["accn"], latest.get("primary_document")),
                                             date=latest["filed"].date(), source="SEC EDGAR")
                fin_evidence = [eid]
            evidence["ev:xbrl"] = EvidenceItem(type="dataset", title="XBRL company facts (SEC)", url=facts_res.urls[0],
                                               source="SEC EDGAR")
            fin_evidence.append("ev:xbrl")
            sources.append(SourceStatus(source="sec_xbrl", available=snap.period_end is not None,
                                        retrieved_at=facts_res.retrieved_at.isoformat(),
                                        data_as_of=snap.period_end.date().isoformat() if snap.period_end is not None else None,
                                        replayed=self.s.sec.mode == "replay"))
        else:
            unavailable["financial"] = facts_res.unavailable_reason
            sources.append(SourceStatus(source="sec_xbrl", available=False, reason=facts_res.unavailable_reason))
        period_end = snap.period_end.date() if snap is not None and snap.period_end is not None else None

        # ---- events (8-K items + event forms)
        events = self._filing_events(filings, int(meta["cik"]), evidence)

        # ---- ML models
        models: dict[str, str] = {}
        distress = self._distress(features, sic, period_end, models)
        segment = self._segment(features, sic, period_end, models)
        fin_anomaly, fin_anomaly_evt = self._financial_anomaly(features, sic, period_end, models, fin_evidence)
        anomalies: list[Anomaly] = [fin_anomaly_evt] if fin_anomaly_evt else []
        forecasts = self._forecasts(store, as_of_ts, models) if store is not None else []

        # ---- news + sentiment
        news_df, news_summary = self._news(news_res, as_of, evidence, models, events)
        sources.append(SourceStatus(source="gdelt_news", available=news_res.available,
                                    retrieved_at=news_res.retrieved_at.isoformat() if news_res.retrieved_at else None,
                                    reason=news_res.unavailable_reason, replayed=self.s.news.mode == "replay"))
        if not news_summary.available:
            unavailable["news"] = news_summary.unavailable_reason

        # ---- market (weekly adjusted history + recent daily data)
        market, market_anoms, price_series, daily_series = None, [], [], []
        daily_df = price_res.data if price_res.available else None
        weekly_df = weekly_res.data if weekly_res.available else None
        if daily_df is not None or weekly_df is not None:
            market = market_metrics(daily_df, weekly_df, etf_res.data if etf_res.available else None, as_of)
            if market:
                src = weekly_res if weekly_df is not None else price_res
                evidence["ev:prices"] = EvidenceItem(type="dataset", title=f"Prices: {market['basis']} ({src.source})",
                                                     url=src.urls[0] if src.urls else None, source=src.source)
                if weekly_df is not None:
                    w = weekly_df[weekly_df.index <= pd.Timestamp(as_of)].iloc[-104:]
                    price_series = [{"date": d.date().isoformat(), "close": round(float(c), 4), "volume": float(v)}
                                    for d, c, v in zip(w.index, w["close"], w["volume"], strict=True)]
                if daily_df is not None:
                    market_anoms = self._market_anomalies(daily_df, as_of, models)
                    dd = daily_df[daily_df.index <= pd.Timestamp(as_of)].iloc[-252:]
                    if len(dd) and (pd.Timestamp(as_of) - dd.index[-1]).days <= 10:
                        daily_series = [{"date": d.date().isoformat(), "close": round(float(c), 4), "volume": float(v)}
                                        for d, c, v in zip(dd.index, dd["close"], dd["volume"], strict=True)]
                if not price_series:
                    price_series = daily_series
            else:
                unavailable["market"] = "price history does not cover the analysis date"
        else:
            unavailable["market"] = weekly_res.unavailable_reason or price_res.unavailable_reason
        sources.append(SourceStatus(source="prices", available=market is not None, reason=unavailable.get("market"),
                                    data_as_of=market.get("last_date") if market else None))
        anomalies.extend(market_anoms)
        recent_mkt = [1.0 for a in market_anoms if (as_of - a.date).days <= 14]  # flagged = top 1% (ML) or |z| >= 5 (rule)

        # ---- employee reviews
        employee = self._employee(ref, as_of, models, evidence)
        sources.append(SourceStatus(source="employee_reviews", available=employee.available, reason=employee.unavailable_reason))
        if not employee.available:
            unavailable["workforce"] = employee.unavailable_reason

        # ---- anomaly events feed the Events pillar (documented penalties)
        if fin_anomaly is not None and fin_anomaly >= 0.95 and period_end:
            latest_periodic = filings[filings["form"].str.match(r"^10-[KQ]")]
            events.append({"id": "evt-stmt-anomaly",
                           "date": latest_periodic.iloc[-1]["filed"].date() if len(latest_periodic) else as_of,
                           "type": "STATEMENT_ANOMALY", "label": "Unusual year-over-year statement changes (ML)",
                           "origin": "financial_anomaly model", "severity": "MEDIUM", "penalty": 10.0, "cap": None,
                           "title": "Statement anomaly score in the top 5%", "evidence": fin_evidence})

        peer_table, peer_date = self.s.peers.table_for(as_of)
        inp = ScoringInputs(
            as_of=as_of, sector=sector, is_bank=bank, features=features, peer_table=peer_table,
            peer_table_date=peer_date, financial_freshness=freshness_for_filing(as_of, period_end),
            financial_evidence=fin_evidence, events=events, news=news_df, market=market,
            employee=({"index": employee.index, "quarter": employee.as_of_quarter, "trend": _esi_trend(employee.series),
                       "freshness": employee_freshness(pd.Period(employee.as_of_quarter).end_time.date(), as_of)}
                      if employee.available else None),
            market_anomaly_max=max(recent_mkt) if recent_mkt else None, financial_anomaly=fin_anomaly,
            distress_band=distress.risk_band, distress_probability=distress.probability_12m)
        if not facts_res.available or snap is None or snap.period_end is None:
            unavailable.setdefault("financial", "no XBRL balance sheet on or before the analysis date")
        health, pillars, _ = score_company(inp, unavailable)
        news_daily = daily_sentiment(news_df) if news_df is not None and len(news_df) else None
        signals = warning_signals(inp, news_daily)

        timeseries = self._timeseries(store, as_of_ts, news_df, news_res, price_series)
        if daily_series:
            timeseries["price_daily"] = daily_series
        history = (self._backfill(store, filings, int(meta["cik"]), sector, sic, as_of)
                   if include_backfill and store is not None else [])
        result = AnalysisResult(
            model_version=f"echo-ml-{__version__}", company=company, case_study=case_study, as_of=as_of,
            generated_at=datetime.now(UTC).isoformat(timespec="seconds"), health=health, pillars=pillars,
            distress=distress, segment=segment, signals=signals,
            events=[Event(id=e["id"], date=e["date"], type=e["type"], label=e["label"], origin=e["origin"],
                          severity=e["severity"], title=e["title"], penalty=e.get("penalty") or 0.0,
                          sentiment=e.get("sentiment"), evidence=e["evidence"])
                    for e in sorted(events, key=lambda e: e["date"], reverse=True)[:150]],
            anomalies=sorted(anomalies, key=lambda a: a.date, reverse=True), forecasts=forecasts, employee=employee,
            news=news_summary, timeseries=timeseries, history=history, evidence=evidence, sources=sources,
            models=models, summary=Summary(text="", generator="pending", grounding_check="pending"))
        if peer_date:
            result.models["peer_stats"] = peer_date
        result.summary = explain(result, self.s.explanation_provider, self.s.anthropic_api_key, self.s.llm_model)
        return result

    # ------------------------------------------------------------------ pieces
    def _filing_events(self, filings: pd.DataFrame, cik: int, evidence: dict) -> list[dict]:
        ev = canonical_events(filings.assign(cik=cik)) if len(filings) else pd.DataFrame()
        events = []
        docs = filings.set_index("accn")["primary_document"].to_dict() if len(filings) else {}
        for row in ev.itertuples():
            eid = _ev_id("filing", row.accn)
            evidence.setdefault(eid, EvidenceItem(type="filing", title=f"{row.source}: {row.label}",
                                                  url=filing_url(cik, row.accn, docs.get(row.accn)),
                                                  date=row.filed.date(), source="SEC EDGAR"))
            events.append({"id": f"evt-{row.accn}-{row.event}", "date": row.filed.date(), "type": row.event,
                           "label": row.label, "origin": row.source, "severity": row.severity,
                           "penalty": float(row.penalty), "cap": None if pd.isna(row.cap) else float(row.cap),
                           "title": row.label, "evidence": [eid]})
        return events

    def _distress(self, features: dict, sic, period_end, models: dict) -> Distress:
        if is_financial_sic(sic):
            return Distress(available=False, unavailable_reason="distress model covers non-financial companies only "
                                                                 "(banks use the bank variant of the Financial pillar)")
        model, card = self.s.registry.get("distress")
        if model is None:
            return Distress(available=False, unavailable_reason="distress model not trained yet")
        if period_end is None:
            return Distress(available=False, unavailable_reason="no financial statements available")
        X = pd.DataFrame([features]).reindex(columns=model.features)
        prob = float(model.predict_proba(X)[0])
        contrib, _ = model.contributions(X)
        order = np.argsort(-np.abs(contrib[0]))[:8]
        drivers = [Driver(feature=model.features[i], label=FEATURE_LABELS.get(model.features[i], model.features[i]),
                          value=_nan_to_none(X.iloc[0, i]), contribution=round(float(contrib[0, i]), 4)) for i in order]
        models["distress"] = card["version"]
        base = card.get("metrics", {}).get("positives", 0) / max(card.get("metrics", {}).get("n", 1), 1)
        return Distress(available=True, probability_12m=round(prob, 5), risk_band=risk_band(prob),
                        model=f"distress v{card['version']} ({card['params']['algorithm']})", base_rate=round(base, 5),
                        drivers=drivers)

    def _segment(self, features, sic, period_end, models) -> Segment:
        model, card = self.s.registry.get("peer_clusters")
        if model is None or period_end is None or is_financial_sic(sic):
            reason = ("segmentation covers non-financial companies only" if is_financial_sic(sic)
                      else "segment model not trained yet" if model is None else "no financial statements")
            return Segment(available=False, unavailable_reason=reason)
        res = model.assign(pd.DataFrame([features]))
        seg = res["segment"].iloc[0]
        models["peer_clusters"] = card["version"]
        return Segment(available=True, segment=seg, membership=round(float(res["membership"].iloc[0]), 3),
                       description=SEGMENT_DESCRIPTIONS.get(seg), model=f"peer_clusters v{card['version']} (k-means)")

    def _financial_anomaly(self, features, sic, period_end, models, evidence_ids):
        model, card = self.s.registry.get("financial_anomaly")
        if model is None or period_end is None:
            return None, None
        X = pd.DataFrame([features])
        if X.reindex(columns=model.features).notna().sum(axis=1).iloc[0] < 6:
            return None, None
        score = float(model.score(X)[0])
        models["financial_anomaly"] = card["version"]
        drivers = ", ".join(f"{FEATURE_LABELS.get(f, f)} ({z:+.1f}σ)" for f, z in model.drivers(X)[0])
        return score, Anomaly(date=period_end, series="financial_statements", score=round(score, 4), kind="ML",
                              note=f"Statement-change anomaly percentile {score * 100:.0f}; largest deviations: {drivers}",
                              model=f"financial_anomaly v{card['version']}")

    def _market_anomalies(self, prices: pd.DataFrame, as_of: date, models) -> list[Anomaly]:
        """ML champion if one passed the promotion gate; otherwise the robust-z rule it was benchmarked against
        (which won on the injection benchmark), labelled Kind=Stat."""
        recent = prices[prices.index <= pd.Timestamp(as_of)]
        if len(recent) < 40 or (pd.Timestamp(as_of) - recent.index[-1]).days > 10:
            return []
        feats = market_feature_frame(recent).iloc[-252:]
        if feats.empty:
            return []
        model, card = self.s.registry.get("market_anomaly")
        if model is not None:
            scores, kind, name = model.score(feats), "ML", f"market_anomaly v{card['version']}"
            flagged = scores >= 0.99
            models["market_anomaly"] = card["version"]
        else:
            max_z = feats[["abs_ret_z", "volume_z", "range_z"]].abs().join(feats["gap_z"].abs()).max(axis=1).to_numpy()
            scores, kind, name = np.clip(max_z / 10.0, 0, 1), "Stat", "robust z-score rule (max |z| >= 5)"
            flagged = max_z >= 5.0
            models["market_anomaly"] = "rule"
        out = []
        for (d, row), s, hit in zip(feats.iterrows(), scores, flagged, strict=True):
            if hit:
                out.append(Anomaly(date=d.date(), series="price_volume", score=round(float(s), 4), kind=kind,
                                   note=f"return {row['ret'] * 100:+.1f}% ({row['ret_z']:+.1f} robust z), "
                                        f"volume {row['volume_z']:+.1f} z", model=name))
        return out

    def _forecasts(self, store: financial.FactStore, as_of_ts, models) -> list[Forecast]:
        out = []
        resolved = known_as_of(store, as_of_ts)
        for item, name in (("Revenue", "revenue_forecast"), ("OperatingCashFlow", "ocf_forecast")):
            model, card = self.s.registry.get(name)
            q = quarterly_series(resolved, item)
            history = [{"period_end": d.date().isoformat(), "value": float(v)} for d, v in q.iloc[-12:].items()]
            if model is None or len(q) < 8:
                continue
            pts = model.predict(q)
            if not pts:
                continue
            models[name] = card["version"]
            out.append(Forecast(series=item, model=f"{name} v{card['version']} (LightGBM + conformal)", history=history,
                                points=[ForecastPoint(**p) for p in pts]))
        return out

    def _news(self, res: SourceResult, as_of: date, evidence: dict, models: dict, events: list[dict]):
        if not res.available or res.data["articles"].empty:
            return None, NewsSummary(available=False, unavailable_reason=res.unavailable_reason or "no relevant headlines")
        arts = res.data["articles"].copy()
        model, card = self.s.registry.get("news_sentiment")
        if model is None:
            return None, NewsSummary(available=False, articles=len(arts), unavailable_reason="sentiment model not trained yet")
        polarity, labels = model.score(arts["title"].tolist())
        arts["polarity"], arts["label"] = polarity, labels
        models["news_sentiment"] = card["version"]
        evidence["ev:news"] = EvidenceItem(type="dataset", title=f"GDELT headlines ({len(arts)} after de-duplication)",
                                           url="https://www.gdeltproject.org/", source="GDELT DOC 2.0")
        rows = []
        for r in arts.sort_values("published_at", ascending=False).itertuples():
            eid = _ev_id("news", r.url or r.title)
            evidence[eid] = EvidenceItem(type="news", title=r.title, url=r.url, date=r.published_at.date(), source=r.domain)
            cls = classify(r.title)
            rows.append({"date": r.published_at.date().isoformat(), "title": r.title, "url": r.url, "source": r.domain,
                         "sentiment": round(float(r.polarity), 3), "label": r.label, "event_type": cls[0] if cls else None,
                         "evidence_id": eid})
            if cls and cls[0] in ("LAYOFFS", "LEGAL_REGULATORY", "CYBER_INCIDENT", "BANKRUPTCY_NEWS", "LEADERSHIP_CHANGE"):
                events.append({"id": f"evt-news-{eid[-10:]}", "date": r.published_at.date(), "type": cls[0],
                               "label": cls[1], "origin": f"News ({r.domain})", "severity": cls[3],
                               "penalty": cls[2] * max(0.0, -float(r.polarity)) if cls[2] else 0.0, "cap": None,
                               "title": r.title, "sentiment": round(float(r.polarity), 3), "evidence": [eid]})
        self._merge_news_events(events)
        summary = NewsSummary(available=True, articles=len(arts), mean_sentiment=round(float(np.mean(polarity)), 4),
                              positive_share=round(float(np.mean(np.array(labels) == "positive")), 4),
                              negative_share=round(float(np.mean(np.array(labels) == "negative")), 4), headlines=rows[:60])
        return arts, summary

    @staticmethod
    def _merge_news_events(events: list[dict]) -> None:
        """One real-world event = one event: news of the same type within 7 days of a filing or of each other merge."""
        news = sorted([e for e in events if e["origin"].startswith("News")], key=lambda e: e["date"])
        keep_ids = set()
        clusters: list[dict] = []
        for e in news:
            match = next((c for c in clusters if c["type"] == e["type"] and abs((c["date"] - e["date"]).days) <= 7), None)
            if match:
                match["evidence"] = (match["evidence"] + e["evidence"])[:10]
                match["penalty"] = max(match["penalty"], e["penalty"])
                continue
            clusters.append(e)
            keep_ids.add(e["id"])
        filings = [e for e in events if not e["origin"].startswith("News")]
        for c in clusters:  # a filing of the same type supersedes the news cluster's penalty
            if any(f["type"] in (c["type"], "RESTRUCTURING" if c["type"] == "LAYOFFS" else "") and
                   abs((f["date"] - c["date"]).days) <= 7 for f in filings):
                c["penalty"] = 0.0
        events[:] = filings + clusters

    def _employee(self, ref, as_of, models, evidence) -> EmployeeSentiment:
        # The review dataset is static, so the (slow: tens of thousands of reviews) index is cached per company,
        # month and model version.
        _, card = self.s.registry.get("review_sentiment")
        key = (ref.market_id, as_of.isoformat()[:7], card["version"] if card else None)
        cached = self._employee_cache.get(key)
        if cached is not None:
            if cached[0].available:
                models["review_sentiment"] = cached[1]
                evidence["ev:reviews"] = cached[2]
            return cached[0]
        result = self._employee_uncached(ref, as_of, models, evidence)
        self._employee_cache[key] = (result, models.get("review_sentiment"), evidence.get("ev:reviews"))
        return result

    def _employee_uncached(self, ref, as_of, models, evidence) -> EmployeeSentiment:
        res = self.s.reviews.reviews(ref, datetime.combine(as_of, datetime.min.time()))
        if not res.available:
            return EmployeeSentiment(available=False, unavailable_reason=res.unavailable_reason)
        model, card = self.s.registry.get("review_sentiment")
        if model is None:
            return EmployeeSentiment(available=False, unavailable_reason="review model not trained yet")
        idx = model.sentiment_index(res.data)
        idx = idx[idx["reviews"] >= 10]
        if idx.empty:
            return EmployeeSentiment(available=False, unavailable_reason="fewer than 10 reviews in every quarter")
        last = idx.iloc[-1]
        models["review_sentiment"] = card["version"]
        evidence["ev:reviews"] = EvidenceItem(type="dataset", title="Kaggle Glassdoor Job Reviews (academic use)",
                                              url=res.urls[0], source="Kaggle")
        return EmployeeSentiment(available=True, index=round(float(last["index"]), 4),
                                 ci90=[round(float(last["ci90_low"]), 4), round(float(last["ci90_high"]), 4)],
                                 as_of_quarter=str(last["quarter"]), reviews=int(idx["reviews"].sum()),
                                 themes=model.themes(res.data.tail(2000))[:6], series=idx.round(4).to_dict("records"))

    def _timeseries(self, store, as_of_ts, news_df, news_res, price_series) -> dict[str, list[dict]]:
        ts: dict[str, list[dict]] = {}
        if store is not None:
            resolved = known_as_of(store, as_of_ts)
            for item in ("Revenue", "NetIncome", "OperatingCashFlow", "OperatingIncome"):
                q = quarterly_series(resolved, item).iloc[-16:]
                ts[f"quarterly_{item}"] = [{"period_end": d.date().isoformat(), "value": float(v)} for d, v in q.items()]
            for item in ("Cash", "TotalLiabilities", "StockholdersEquity", "TotalAssets"):
                s = financial.instant_series(resolved, item).iloc[-12:]
                ts[f"balance_{item}"] = [{"period_end": d.date().isoformat(), "value": float(v)} for d, v in s.items()]
        if news_df is not None and len(news_df):
            daily = news_df.assign(day=news_df["published_at"].dt.tz_convert(None).dt.normalize()).groupby("day").agg(
                sentiment=("polarity", "mean"), articles=("title", "size"))
            ts["news_sentiment"] = [{"date": d.date().isoformat(), "sentiment": round(float(r.sentiment), 4),
                                     "articles": int(r.articles)} for d, r in daily.iterrows()]
        if news_res.available and len(news_res.data["volume"]):
            ts["news_volume"] = [{"date": d.date().isoformat(), "articles": int(a)}
                                 for d, a in zip(news_res.data["volume"]["date"], news_res.data["volume"]["articles"], strict=True)]
        if price_series:
            ts["price"] = price_series
        return ts

    def _backfill(self, store, filings, cik, sector, sic, as_of: date) -> list[dict]:
        """Point-in-time history: Financial + Events pillars (and the distress model) at each 10-K/10-Q filing date in
        the last 3 years. News/market are excluded because their history is not available, so these points are
        labelled as a partial score."""
        out = []
        dates = filings[filings["form"].str.match(r"^10-[KQ]$") & (filings["filed"] >= pd.Timestamp(as_of) - pd.Timedelta(days=3 * 365))]
        events_all = self._filing_events(filings, cik, {})
        bank = is_bank_sic(sic)
        model, _ = self.s.registry.get("distress")
        for row in dates.itertuples():
            d = row.filed.date()
            feats, snap = financial.build(store, row.filed,
                                          latest_filing=(row.report_date, row.filed) if pd.notna(row.report_date) else None)
            if snap.period_end is None:
                continue
            if bank:
                feats.update(bank_features(snap))
            table, _ = self.s.peers.table_for(d)
            inp = ScoringInputs(as_of=d, sector=sector, is_bank=bank, features=feats, peer_table=table, peer_table_date=None,
                                financial_freshness=1.0, financial_evidence=[], events=[e for e in events_all if e["date"] <= d],
                                news=None, market=None, employee=None)
            health, pillars, _ = score_company(inp, {})
            fin = next(p for p in pillars if p.key == "financial")
            evt = next(p for p in pillars if p.key == "events")
            partial = None
            if fin.score is not None:
                partial = round((0.30 * fin.score + 0.15 * evt.score) / 0.45, 2)
            prob = None
            if model is not None and not is_financial_sic(sic):
                X = pd.DataFrame([feats]).reindex(columns=model.features)
                prob = round(float(model.predict_proba(X)[0]), 5)
            out.append({"as_of": d.isoformat(), "form": row.form, "partial_score": partial, "financial": fin.score,
                        "events": evt.score, "distress_probability": prob})
        return out


def _esi_trend(series: list[dict]) -> float | None:
    """Theil-Sen slope of the last 4 quarterly Employee Sentiment Index values (index points per quarter)."""
    values = [row["index"] for row in series[-4:]]
    if len(values) < 4:
        return None
    slopes = [(values[j] - values[i]) / (j - i) for i in range(4) for j in range(i + 1, 4)]
    return round(float(np.median(slopes)), 4)


def feature_vector(result_features: dict) -> dict:
    return {k: _nan_to_none(result_features.get(k)) for k in FIN_FEATURES}


def load_universe_mapping() -> dict:
    return load_mapping("sec_8k_items.yaml")
