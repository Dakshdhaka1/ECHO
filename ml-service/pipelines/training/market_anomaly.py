"""M5a market anomaly detection (ML_PIPELINE §4).

Isolation Forest on daily robust-z vectors (return, |return|, volume, intraday range, overnight gap),
compared with the max-|z| rule baseline. Data: every price file in data/raw/prices (recorded with an
Alpha Vantage key) plus IBM's full history, which Alpha Vantage serves with its public demo key.
Time split per ticker: fit <= split_year, evaluate after. Evaluation:
  1. injected shocks in the test period (synthetic, labelled) - PR-AUC, recall@k;
  2. real known events - hit rate on earnings-release days (8-K Item 2.02) vs the base rate.

    python -m pipelines.run market_anomaly
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.adapters.prices import adjust_splits
from app.inference.anomaly import MARKET_ANOMALY_FEATURES, IsolationScorer, market_feature_frame
from pipelines.common import PROCESSED_DIR, RAW_DIR, SEED, set_seed, update_manifest
from pipelines.evaluation.metrics import plot_curves, report_dir
from pipelines.mlops import TrainingRun, finish_run

log = logging.getLogger("echo.training.market_anomaly")
MODEL = "market_anomaly"
PRICE_DIR = RAW_DIR / "prices"
DEMO_URL = "https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol=IBM&outputsize=full&apikey=demo"
TICKER_CIK = {"IBM": 51143}


def ensure_ibm() -> None:
    path = PRICE_DIR / "IBM.csv"
    if path.exists():
        return
    data = httpx.get(DEMO_URL, timeout=60).json()["Time Series (Daily)"]
    df = pd.DataFrame.from_dict(data, orient="index")
    df.columns = ["open", "high", "low", "close", "volume"]
    df.index.name = "date"
    PRICE_DIR.mkdir(parents=True, exist_ok=True)
    df.reset_index().to_csv(path, index=False)
    update_manifest(RAW_DIR / "MANIFEST.json", path, DEMO_URL.replace("apikey=demo", "apikey=<demo>"))


def load_series() -> dict[str, pd.DataFrame]:
    ensure_ibm()
    series = {}
    for path in sorted(PRICE_DIR.glob("*.csv")):
        df = pd.read_csv(path)
        df.columns = [c.lower() for c in df.columns]
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()[["open", "high", "low", "close", "volume"]].astype(float)
        adjusted, _ = adjust_splits(df)
        series[path.stem] = market_feature_frame(adjusted)
    return series


def earnings_days(ticker: str) -> set[pd.Timestamp]:
    cik = TICKER_CIK.get(ticker)
    path = PROCESSED_DIR / "sec" / "filings.parquet"
    if cik is None or not path.exists():
        return set()
    f = pd.read_parquet(path, columns=["cik", "form", "filed", "items"])
    f = f[(f["cik"] == cik) & f["form"].str.startswith("8-K") & f["items"].str.contains("2.02", regex=False)]
    return set(f["filed"].dt.normalize())


def inject(X: pd.DataFrame, frac: float, rng: np.random.Generator) -> tuple[pd.DataFrame, np.ndarray]:
    X = X.copy()
    idx = rng.choice(len(X), size=max(1, int(len(X) * frac)), replace=False)
    kind = rng.integers(0, 3, size=len(idx))
    rows = X.index[idx]
    sign = rng.choice([-1, 1], size=len(idx))
    shock = (kind == 0)   # price shock with volume
    X.loc[rows[shock], "ret_z"] = sign[shock] * rng.uniform(4, 8, shock.sum())
    X.loc[rows[shock], "volume_z"] += rng.uniform(2, 5, shock.sum())
    vol = (kind == 1)     # volume surge without a price move (e.g. block trade, news leak)
    X.loc[rows[vol], "volume_z"] += rng.uniform(4, 7, vol.sum())
    gap = (kind == 2)     # overnight gap that partly reverts intraday (wide range)
    X.loc[rows[gap], "gap_z"] = sign[gap] * rng.uniform(4, 7, gap.sum())
    X.loc[rows[gap], "range_z"] += rng.uniform(3, 5, gap.sum())
    X["abs_ret_z"] = X["ret_z"].abs()
    y = np.zeros(len(X), dtype=int)
    y[idx] = 1
    return X, y


def zscore_baseline(X: pd.DataFrame) -> np.ndarray:
    return X[["abs_ret_z", "volume_z", "range_z"]].abs().join(X["gap_z"].abs()).max(axis=1).to_numpy()


def train(config: dict) -> dict:
    set_seed()
    series = load_series()
    split = pd.Timestamp(f"{config['split_year']}-12-31")
    train_parts = [s[s.index <= split] for s in series.values()]
    test_parts = {t: s[s.index > split] for t, s in series.items()}
    X_tr = pd.concat(train_parts)[MARKET_ANOMALY_FEATURES]
    pre = Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]).fit(X_tr)
    forest = IsolationForest(n_estimators=config["n_estimators"], random_state=SEED, n_jobs=-1)
    forest.fit(pre.transform(X_tr))
    scorer = IsolationScorer(pre, forest, MARKET_ANOMALY_FEATURES, -forest.score_samples(pre.transform(X_tr)))

    rng = np.random.default_rng(SEED)
    X_te = pd.concat(test_parts.values())[MARKET_ANOMALY_FEATURES].reset_index(drop=True)
    # Real extreme days (earnings gaps, crashes) are unlabelled anomalies: counting them as negatives would punish
    # both detectors for finding real events, so the injection benchmark runs on the remaining "ordinary" days.
    ordinary = zscore_baseline(X_te) < config["background_max_z"]
    X_bg = X_te[ordinary].reset_index(drop=True)
    X_inj, y_inj = inject(X_bg, config["inject_fraction"], rng)
    scores = {"isolation_forest": scorer.raw(X_inj), "max_abs_z_baseline": zscore_baseline(X_inj)}
    k = int(y_inj.sum())
    injected = {n: {"pr_auc": float(average_precision_score(y_inj, s)), "roc_auc": float(roc_auc_score(y_inj, s)),
                    "recall_at_k": float(y_inj[np.argsort(-s)[:k]].sum() / k)} for n, s in scores.items()}
    log.info("injection benchmark: %s", injected)

    # real events: earnings-release days (filed date or next trading day) among the top 5% scores
    real = {}
    for ticker, te in test_parts.items():
        days = earnings_days(ticker)
        if not days:
            continue
        idx = te.index.normalize()
        is_event = idx.isin(list(days)) | idx.isin([d + pd.Timedelta(days=1) for d in days])
        for name, s in {"isolation_forest": scorer.raw(te), "max_abs_z_baseline": zscore_baseline(te)}.items():
            flagged = s >= np.quantile(s, 0.95)
            real.setdefault(name, {})[ticker] = {
                "event_days": int(is_event.sum()), "hit_rate_top5pct": float(flagged[is_event].mean()),
                "base_rate_top5pct": 0.05, "lift": float(flagged[is_event].mean() / 0.05)}
    log.info("earnings-day hit rate: %s", real)
    out = report_dir(MODEL)
    fig = plot_curves(y_inj, scores, out / "injection_curves.png", "Market anomaly - injected shocks (test period)")

    def smoke(d: Path) -> None:
        m = joblib.load(d / "model.joblib")
        s = m.score(X_te.head(10))
        assert s.shape == (10,) and np.all((s >= 0) & (s <= 1))

    run = TrainingRun(
        model_name=MODEL, kind="ML", primary_metric="injected_pr_auc",
        metrics={"injected_pr_auc": injected["isolation_forest"]["pr_auc"],
                 "injected_roc_auc": injected["isolation_forest"]["roc_auc"],
                 "injected_recall_at_k": injected["isolation_forest"]["recall_at_k"]},
        baseline={"name": "max_abs_z_baseline", "metrics": {"injected_pr_auc": injected["max_abs_z_baseline"]["pr_auc"]}},
        params={"n_estimators": config["n_estimators"], "features": MARKET_ANOMALY_FEATURES, "window_days": 60},
        data={"tickers": sorted(series), "train_days": len(X_tr), "test_days": len(X_te),
              "split_year": config["split_year"], "inject_fraction": config["inject_fraction"],
              "background_days": int(ordinary.sum()), "excluded_extreme_days": int((~ordinary).sum())},
        intended_use="Flag trading days whose return/volume/range/gap pattern is unusual for the stock's own recent "
                     "history (robust z-scores), shown as anomaly alerts on the Market tab.",
        limitations="Trained on the price histories available without a paid licence (IBM via the Alpha Vantage demo "
                    "key plus locally recorded tickers). News-volume and sentiment anomalies use separate statistical "
                    "rules because no long news history is available for training.",
        licences={"data": "Alpha Vantage free API (not redistributed; recorded locally only, licence L1)"},
        save=lambda d: joblib.dump(scorer, d / "model.joblib", compress=3), smoke_test=smoke,
        figures={"injection_curves": fig}, tables={"injection": injected, "earnings_days": real},
    )
    return finish_run(run, config)
