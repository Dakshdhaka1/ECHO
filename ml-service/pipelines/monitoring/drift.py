"""Monitoring (ML_PIPELINE §7.4): input drift (PSI), prediction drift and data freshness.

The inference service appends one row per analysis to a SQLite log; this job compares the logged
feature/prediction distributions with the reference histograms saved alongside each model at
training time and writes artifacts/monitoring/<date>.json. A PSI above 0.2 on a model input, or a
stale data source, sets `retrain_recommended`, which the backend's scheduled retraining checks.

    python -m pipelines.monitoring.drift [--days 30]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

PSI_ALERT = 0.2
PSI_WARN = 0.1
MIN_ROWS = 20


def reference_histogram(values: pd.Series, bins: int = 10) -> dict | None:
    """Decile bin edges and training proportions for one feature (NaN share kept as its own bucket)."""
    v = values.replace([np.inf, -np.inf], np.nan)
    finite = v.dropna().to_numpy()
    if len(finite) < 50:
        return None
    edges = np.unique(np.quantile(finite, np.linspace(0, 1, bins + 1)[1:-1]))
    counts = np.bincount(np.searchsorted(edges, finite, side="right"), minlength=len(edges) + 1)
    return {"edges": edges.tolist(), "proportions": (counts / len(finite)).tolist(), "nan_share": float(v.isna().mean())}


def psi(reference: dict, live: np.ndarray) -> float:
    edges = np.asarray(reference["edges"])
    finite = live[np.isfinite(live)]
    if len(finite) == 0:
        return float("nan")
    counts = np.bincount(np.searchsorted(edges, finite, side="right"), minlength=len(edges) + 1)
    actual = np.clip(counts / len(finite), 1e-4, None)
    expected = np.clip(np.asarray(reference["proportions"]), 1e-4, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


class InferenceLog:
    """Append-only SQLite log of model inputs/outputs per analysis (no personal data)."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as con:
            con.execute("""CREATE TABLE IF NOT EXISTS inference (
                logged_at TEXT, company TEXT, as_of TEXT, model TEXT, version TEXT,
                features TEXT, prediction REAL, extra TEXT)""")

    def append(self, company: str, as_of: str, model: str, version: str, features: dict, prediction: float | None,
               extra: dict | None = None) -> None:
        clean = {k: (None if v is None or (isinstance(v, float) and not np.isfinite(v)) else float(v))
                 for k, v in features.items()}
        with self._lock, sqlite3.connect(self.path) as con:
            con.execute("INSERT INTO inference VALUES (?,?,?,?,?,?,?,?)",
                        (datetime.now(UTC).isoformat(), company, as_of, model, version, json.dumps(clean),
                         prediction, json.dumps(extra or {})))

    def frame(self, since_days: int) -> pd.DataFrame:
        since = (datetime.now(UTC) - timedelta(days=since_days)).isoformat()
        with sqlite3.connect(self.path) as con:
            return pd.read_sql_query("SELECT * FROM inference WHERE logged_at >= ?", con, params=(since,))


def run(model_dir: Path, log_path: Path, days: int = 30) -> dict:
    log = InferenceLog(log_path)
    df = log.frame(days)
    report: dict = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "window_days": days,
                    "rows": len(df), "models": {}, "retrain_recommended": [], "thresholds": {"psi_alert": PSI_ALERT}}
    for model_name, group in df.groupby("model"):
        pointer = model_dir / model_name / "CHAMPION"
        ref_path = model_dir / model_name / pointer.read_text().strip() / "reference.json" if pointer.exists() else None
        entry: dict = {"rows": len(group), "companies": int(group["company"].nunique())}
        if ref_path is None or not ref_path.exists():
            entry["status"] = "no reference histogram"
            report["models"][model_name] = entry
            continue
        ref = json.loads(ref_path.read_text())
        if len(group) < MIN_ROWS:
            entry["status"] = f"insufficient data (< {MIN_ROWS} inferences in window)"
            report["models"][model_name] = entry
            continue
        feats = pd.DataFrame([json.loads(f) for f in group["features"]])
        per_feature = {}
        for name, hist in ref.get("features", {}).items():
            if name in feats:
                per_feature[name] = round(psi(hist, feats[name].astype(float).to_numpy()), 4)
        entry["psi"] = dict(sorted(per_feature.items(), key=lambda kv: -(kv[1] if np.isfinite(kv[1]) else -1)))
        drifted = [k for k, v in per_feature.items() if np.isfinite(v) and v > PSI_ALERT]
        entry["drifted_features"] = drifted
        if "prediction" in ref and group["prediction"].notna().sum() >= MIN_ROWS:
            entry["prediction_psi"] = round(psi(ref["prediction"], group["prediction"].astype(float).to_numpy()), 4)
            if entry["prediction_psi"] > PSI_ALERT:
                drifted.append("prediction")
        entry["status"] = "drift" if drifted else "ok"
        if drifted:
            report["retrain_recommended"].append(model_name)
        report["models"][model_name] = entry
    freshness = {}
    for company, g in df.groupby("company"):
        extra = [json.loads(e) for e in g["extra"]]
        ages = [e.get("financials_age_days") for e in extra if e.get("financials_age_days") is not None]
        if ages:
            freshness[company] = {"financials_age_days": int(ages[-1]), "stale": ages[-1] > 456}
    report["freshness"] = freshness
    out = model_dir / "monitoring" / f"{datetime.now(UTC).date().isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    return report


def latest_report(model_dir: Path) -> dict | None:
    files = sorted((model_dir / "monitoring").glob("20*.json"))
    return json.loads(files[-1].read_text()) if files else None


if __name__ == "__main__":
    from app.core.config import get_settings

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    settings = get_settings()
    print(json.dumps(run(settings.model_dir, settings.monitoring_db, parser.parse_args().days), indent=2))
