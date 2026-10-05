"""M5b financial-statement anomaly detection (ML_PIPELINE §4).

Isolation Forest over year-over-year forensic indices (Beneish's eight + growth/margin/liquidity
changes) of each 10-K. Evaluated two ways on the 2020-2024 test years (model fitted on 2010-2019):
  1. real outcome: does the score rank companies that later file an 8-K Item 4.02 restatement
     (within 12 months) higher? Compared with the Beneish M-score alone.
  2. synthetic injection: distort a random 2% of test rows the way manipulation typically shows up
     (receivables, margins, accruals) and measure recall@k / ROC-AUC.

    python -m pipelines.run financial_anomaly
"""

from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from app.inference.anomaly import FINANCIAL_ANOMALY_FEATURES, IsolationScorer, signed_log
from pipelines.common import PROCESSED_DIR, RAW_DIR, REPO_ROOT, SEED, manifest_hash, set_seed
from pipelines.evaluation.metrics import plot_curves, report_dir
from pipelines.features.events import canonical_events
from pipelines.mlops import TrainingRun, finish_run

log = logging.getLogger("echo.training.financial_anomaly")
MODEL = "financial_anomaly"


def restatement_labels(df: pd.DataFrame) -> np.ndarray:
    filings = pd.read_parquet(PROCESSED_DIR / "sec" / "filings.parquet", columns=["cik", "accn", "filed", "form", "items"])
    filings = filings[filings["cik"].isin(df["cik"].unique())]
    ev = canonical_events(filings)
    ev = ev[ev["event"] == "RESTATEMENT"][["cik", "filed"]]
    by_cik = ev.groupby("cik")["filed"].apply(lambda s: s.to_numpy()).to_dict()
    labels = []
    for cik, as_of in zip(df["cik"], df["as_of"], strict=True):
        dates = by_cik.get(cik)
        labels.append(int(dates is not None and np.any((dates > as_of) & (dates <= as_of + pd.Timedelta(days=365)))))
    return np.array(labels)


def precision_at(y: np.ndarray, score: np.ndarray, frac: float) -> float:
    k = max(1, int(len(y) * frac))
    return float(y[np.argsort(-score)[:k]].mean())


def inject(X: pd.DataFrame, frac: float, rng: np.random.Generator) -> tuple[pd.DataFrame, np.ndarray]:
    """Apply typical manipulation footprints to a random subset (labelled synthetic, ML_PIPELINE §8)."""
    X = X.copy()
    idx = rng.choice(len(X), size=max(1, int(len(X) * frac)), replace=False)
    pattern = rng.integers(0, 3, size=len(idx))
    rows = X.index[idx]
    X.loc[rows[pattern == 0], "bn_dsri"] = X.loc[rows[pattern == 0], "bn_dsri"].fillna(1) * rng.uniform(2.5, 4, (pattern == 0).sum())
    X.loc[rows[pattern == 1], "bn_tata"] = X.loc[rows[pattern == 1], "bn_tata"].fillna(0) + rng.uniform(0.15, 0.3, (pattern == 1).sum())
    X.loc[rows[pattern == 2], "bn_gmi"] = X.loc[rows[pattern == 2], "bn_gmi"].fillna(1) * rng.uniform(1.8, 3, (pattern == 2).sum())
    X.loc[rows[pattern == 2], "bn_sgi"] = X.loc[rows[pattern == 2], "bn_sgi"].fillna(1) * rng.uniform(1.6, 2.5, (pattern == 2).sum())
    y = np.zeros(len(X), dtype=int)
    y[idx] = 1
    return X, y


def train(config: dict) -> dict:
    set_seed()
    df = pd.read_parquet(REPO_ROOT / config["dataset"])
    df = df[df[FINANCIAL_ANOMALY_FEATURES].notna().sum(axis=1) >= 6].reset_index(drop=True)
    tr = df[df["year"].between(*config["split"]["train"])]
    te = df[df["year"].between(*config["split"]["test"])].reset_index(drop=True)
    pre = Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", RobustScaler(quantile_range=(10, 90)))])
    X_tr = signed_log(tr[FINANCIAL_ANOMALY_FEATURES].astype(float).replace([np.inf, -np.inf], np.nan))
    pre.fit(X_tr)
    forest = IsolationForest(n_estimators=config["n_estimators"], contamination="auto", random_state=SEED, n_jobs=-1)
    forest.fit(pre.transform(X_tr))
    scorer = IsolationScorer(pre, forest, FINANCIAL_ANOMALY_FEATURES, -forest.score_samples(pre.transform(X_tr)),
                             transform="signed_log")

    # 1) real outcome: later restatements
    y_restate = restatement_labels(te)
    s_if = scorer.raw(te)
    beneish = te["beneish_m"].fillna(te["beneish_m"].median()).to_numpy()
    real = {}
    for name, s in {"isolation_forest": s_if, "beneish_m_baseline": beneish}.items():
        real[name] = {"roc_auc": float(roc_auc_score(y_restate, s)), "pr_auc": float(average_precision_score(y_restate, s)),
                      "precision_at_5pct": precision_at(y_restate, s, 0.05),
                      "lift_at_5pct": precision_at(y_restate, s, 0.05) / max(y_restate.mean(), 1e-9)}
    for v in real.values():
        v["lift_at_5pct"] = float(v["lift_at_5pct"])
    real["base_rate"] = float(y_restate.mean())
    real["positives"] = int(y_restate.sum())
    log.info("restatement evaluation: %s", real)

    # 2) synthetic injection benchmark
    rng = np.random.default_rng(SEED)
    X_inj, y_inj = inject(te[FINANCIAL_ANOMALY_FEATURES].astype(float), config["inject_fraction"], rng)
    inj_scores = {"isolation_forest": scorer.raw(X_inj)}
    te_inj = te.copy()
    te_inj[FINANCIAL_ANOMALY_FEATURES] = X_inj
    # Beneish M recomputed from the injected indices (same coefficients as pipelines.features.financial)
    b = X_inj.fillna(X_inj.median())
    inj_scores["beneish_m_baseline"] = (-4.84 + 0.92 * b["bn_dsri"] + 0.528 * b["bn_gmi"] + 0.404 * b["bn_aqi"]
                                        + 0.892 * b["bn_sgi"] + 0.115 * b["bn_depi"] - 0.172 * b["bn_sgai"]
                                        + 4.679 * b["bn_tata"] - 0.327 * b["bn_lvgi"]).to_numpy()
    injected = {}
    k = int(y_inj.sum())
    for name, s in inj_scores.items():
        top = np.argsort(-s)[:k]
        injected[name] = {"roc_auc": float(roc_auc_score(y_inj, s)), "pr_auc": float(average_precision_score(y_inj, s)),
                          "recall_at_k": float(y_inj[top].sum() / k)}
    log.info("injection benchmark: %s", injected)
    out = report_dir(MODEL)
    fig = plot_curves(y_inj, inj_scores, out / "injection_curves.png", "Financial anomaly - injected distortions (test years)")

    def smoke(d: Path) -> None:
        m = joblib.load(d / "model.joblib")
        s = m.score(te.head(10))
        assert s.shape == (10,) and np.all((s >= 0) & (s <= 1))
        assert len(m.drivers(te.head(2))) == 2

    run = TrainingRun(
        model_name=MODEL, kind="ML", primary_metric="restatement_roc_auc",
        metrics={"injected_pr_auc": injected["isolation_forest"]["pr_auc"],
                 "injected_roc_auc": injected["isolation_forest"]["roc_auc"],
                 "injected_recall_at_k": injected["isolation_forest"]["recall_at_k"],
                 "restatement_roc_auc": real["isolation_forest"]["roc_auc"],
                 "restatement_lift_at_5pct": real["isolation_forest"]["lift_at_5pct"]},
        baseline={"name": "beneish_m_baseline",
                  "metrics": {"restatement_roc_auc": real["beneish_m_baseline"]["roc_auc"],
                              "restatement_lift_at_5pct": real["beneish_m_baseline"]["lift_at_5pct"],
                              "injected_pr_auc": injected["beneish_m_baseline"]["pr_auc"]}},
        params={"n_estimators": config["n_estimators"], "features": FINANCIAL_ANOMALY_FEATURES,
                "preprocessing": "signed log + median impute + robust scale"},
        data={"train_rows": len(tr), "test_rows": len(te), "split": config["split"],
              "inject_fraction": config["inject_fraction"], "manifest_sha256": manifest_hash(RAW_DIR / "MANIFEST.json")},
        intended_use="Flag 10-K/10-Q statements whose year-over-year changes are unusual relative to the market, "
                     "as a prompt for closer reading (e.g. receivables or accruals growing much faster than revenue).",
        limitations="An anomaly is not evidence of misstatement. Real restatements are rare and only weakly "
                    "predictable from aggregated statements; the injection benchmark is synthetic by construction.",
        licences={"data": "SEC EDGAR, public domain"},
        save=lambda d: joblib.dump(scorer, d / "model.joblib", compress=3), smoke_test=smoke,
        figures={"injection_curves": fig}, tables={"restatements": real, "injection": injected},
    )
    return finish_run(run, config)
