"""M6 fundamentals forecasting (ML_PIPELINE §4): next 4 quarters of a canonical item.

Rolling-origin evaluation on real SEC quarterly series:
  train       targets ending <= train_end
  calibration targets in (train_end, calib_end]   -> split-conformal 80% intervals per horizon
  test        targets in (calib_end, test_end]     -> MASE, sMAPE, interval coverage
Baselines on the same test origins: naive (last value), seasonal naive (same quarter last year),
and ETS (Holt-Winters, damped additive trend + additive seasonality) fitted per series per origin.

    python -m pipelines.run revenue_forecast
"""

from __future__ import annotations

import json
import logging
import warnings
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from app.inference.forecast import (
    FEATURES,
    HORIZONS,
    N_LAGS,
    ForecastModel,
    origin_features,
    regular_quarters,
)
from pipelines.common import PROCESSED_DIR, RAW_DIR, SEED, is_financial_sic, manifest_hash, set_seed
from pipelines.evaluation.metrics import report_dir
from pipelines.features.financial import known_as_of, quarterly_series
from pipelines.mlops import TrainingRun, finish_run

log = logging.getLogger("echo.training.forecast")


def load_series(item: str, max_series: int, workers: int) -> dict[int, pd.Series]:
    """Quarterly series of one canonical item for every non-financial company (read once, in-process)."""
    companies = pd.read_parquet(PROCESSED_DIR / "sec" / "companies.parquet", columns=["cik", "sic"])
    keep = set(companies.loc[companies["sic"].notna() & ~companies["sic"].map(is_financial_sic), "cik"])
    facts = pq.read_table(PROCESSED_DIR / "sec" / "facts.parquet", filters=[("item", "=", item)]).to_pandas()
    facts = facts[facts["cik"].isin(keep)]
    series: dict[int, pd.Series] = {}
    for cik, f in facts.groupby("cik"):
        q = regular_quarters(quarterly_series(known_as_of(f, pd.Timestamp("2100-01-01")), item))
        if len(q) >= N_LAGS + 6:
            series[int(cik)] = q
    keys = sorted(series)
    rng = np.random.default_rng(SEED)
    if len(keys) > max_series:
        keys = sorted(rng.choice(keys, size=max_series, replace=False).tolist())
    return {k: series[k] for k in keys}


def build_rows(series: dict[int, pd.Series]) -> pd.DataFrame:
    rows = []
    for cik, s in series.items():
        values, ends = s.to_numpy(dtype=float), s.index
        for t in range(N_LAGS - 1, len(values) - 1):
            for h in HORIZONS:
                if t + h >= len(values):
                    break
                f = origin_features(values[: t + 1], ends[t], h)
                if f is None:
                    continue
                scale = f.pop("_scale")
                # MASE scale: mean |seasonal difference| in the history available at the origin
                hist = values[: t + 1]
                mase_scale = float(np.mean(np.abs(hist[4:] - hist[:-4]))) if len(hist) > 4 else np.nan
                rows.append({**f, "cik": cik, "origin": ends[t], "target_end": ends[t + h], "scale": scale,
                             "y": values[t + h], "target": values[t + h] / scale, "last": values[t],
                             "seasonal": values[t + h - 4], "mase_scale": mase_scale})
    return pd.DataFrame(rows)


def _ets_forecast(args: tuple[np.ndarray, int]) -> list[float]:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    hist, n = args
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            fit = ExponentialSmoothing(hist, trend="add", damped_trend=True, seasonal="add", seasonal_periods=4,
                                       initialization_method="estimated").fit(optimized=True)
            return list(fit.forecast(n))
        except Exception:
            return [float(hist[-1])] * n


def ets_baseline(test: pd.DataFrame, series: dict[int, pd.Series], workers: int, sample: int) -> pd.Series:
    origins = test[["cik", "origin"]].drop_duplicates()
    rng = np.random.default_rng(SEED)
    keep = rng.choice(len(origins), size=min(sample, len(origins)), replace=False)
    origins = origins.iloc[np.sort(keep)]
    jobs = [(series[c][series[c].index <= o].to_numpy(dtype=float), 4) for c, o in zip(origins["cik"], origins["origin"], strict=True)]
    with ProcessPoolExecutor(workers) as pool:
        forecasts = list(pool.map(_ets_forecast, jobs, chunksize=50))
    pred = {}
    for (c, o), fc in zip(zip(origins["cik"], origins["origin"], strict=True), forecasts, strict=True):
        for h, v in enumerate(fc, start=1):
            pred[(c, o, h)] = v
    return pd.Series([pred.get((c, o, h), np.nan) for c, o, h in zip(test["cik"], test["origin"], test["horizon"], strict=True)],
                     index=test.index)


def score(y, yhat, mase_scale) -> dict:
    y, yhat, mase_scale = map(np.asarray, (y, yhat, mase_scale))
    ok = np.isfinite(yhat) & np.isfinite(mase_scale) & (mase_scale > 0)
    err = np.abs(y[ok] - yhat[ok])
    return {"mase": float(np.mean(err / mase_scale[ok])),
            "smape": float(np.mean(2 * err / np.maximum(np.abs(y[ok]) + np.abs(yhat[ok]), 1e-9))), "n": int(ok.sum())}


def train(config: dict) -> dict:
    set_seed()
    item, model_name = config["item"], config["model"]
    series = load_series(item, config["max_series"], config["workers"])
    rows = build_rows(series)
    te_mask = (rows["target_end"] > config["calib_end"]) & (rows["target_end"] <= config["test_end"]) & (rows["origin"] <= config["calib_end"])
    tr = rows[rows["target_end"] <= config["train_end"]]
    ca = rows[(rows["target_end"] > config["train_end"]) & (rows["target_end"] <= config["calib_end"]) & (rows["origin"] <= config["train_end"])]
    te = rows[te_mask].copy()
    log.info("%s series=%d rows train/calib/test=%d/%d/%d", item, len(series), len(tr), len(ca), len(te))

    model = lgb.LGBMRegressor(objective="huber", alpha=1.0, n_estimators=config["n_estimators"], learning_rate=0.03,
                              num_leaves=63, min_child_samples=100, subsample=0.8, subsample_freq=1,
                              colsample_bytree=0.9, random_state=SEED, n_jobs=-1, verbose=-1)
    model.fit(tr[FEATURES], tr["target"].clip(-5, 5))
    resid = (ca["target"] - model.predict(ca[FEATURES]))
    quantiles = {h: (float(np.quantile(resid[ca["horizon"] == h], 0.10)), float(np.quantile(resid[ca["horizon"] == h], 0.90)))
                 for h in HORIZONS}
    forecaster = ForecastModel(model, quantiles, item)

    te["lgbm"] = model.predict(te[FEATURES]) * te["scale"]
    te["ets"] = ets_baseline(te, series, config["workers"], config["ets_sample_origins"])
    lo = np.array([quantiles[h][0] for h in te["horizon"]])
    hi = np.array([quantiles[h][1] for h in te["horizon"]])
    pred_scaled = te["lgbm"] / te["scale"]
    covered = ((te["target"] >= pred_scaled + lo) & (te["target"] <= pred_scaled + hi)).mean()

    results, ets_rows = {}, te[te["ets"].notna()]
    for name, col in (("naive", "last"), ("seasonal_naive", "seasonal"), ("lightgbm_global", "lgbm")):
        results[name] = {"all": score(te["y"], te[col], te["mase_scale"]),
                         "ets_subset": score(ets_rows["y"], ets_rows[col], ets_rows["mase_scale"]),
                         "by_horizon": {int(h): score(g["y"], g[col], g["mase_scale"]) for h, g in te.groupby("horizon")}}
    results["ets"] = {"ets_subset": score(ets_rows["y"], ets_rows["ets"], ets_rows["mase_scale"]),
                      "by_horizon": {int(h): score(g["y"], g["ets"], g["mase_scale"]) for h, g in ets_rows.groupby("horizon")}}
    results["interval_coverage_80"] = float(covered)
    log.info("forecast results: %s", json.dumps({k: v.get("all", v.get("ets_subset")) if isinstance(v, dict) else v
                                                for k, v in results.items()}))
    baseline_name = min(("seasonal_naive", "naive"), key=lambda b: results[b]["all"]["mase"])
    out = report_dir(model_name)
    (out / "results.json").write_text(json.dumps(results, indent=2))

    def smoke(d: Path) -> None:
        m = joblib.load(d / "model.joblib")
        s = next(iter(series.values()))
        fc = m.predict(s)
        assert len(fc) == 4 and all(f["p10"] <= f["p50"] <= f["p90"] for f in fc)

    run = TrainingRun(
        model_name=model_name, kind="ML", primary_metric="mase", lower_is_better=True,
        metrics={"mase": results["lightgbm_global"]["all"]["mase"], "smape": results["lightgbm_global"]["all"]["smape"],
                 "mase_ets_subset": results["lightgbm_global"]["ets_subset"]["mase"],
                 "interval_coverage_80": float(covered)},
        baseline={"name": baseline_name, "metrics": {"mase": results[baseline_name]["all"]["mase"],
                                                     "smape": results[baseline_name]["all"]["smape"]},
                  "ets_subset_mase": results["ets"]["ets_subset"]["mase"]},
        params={"item": item, "n_lags": N_LAGS, "horizons": list(HORIZONS), "objective": "huber",
                "n_estimators": config["n_estimators"], "intervals": "split conformal (10th/90th residual quantiles)"},
        data={"series": len(series), "rows": {"train": len(tr), "calibration": len(ca), "test": len(te)},
              "split": {k: config[k] for k in ("train_end", "calib_end", "test_end")},
              "source": "SEC XBRL quarterly values (Q4 derived as FY - 9M)",
              "manifest_sha256": manifest_hash(RAW_DIR / "MANIFEST.json")},
        intended_use=f"Forecast the next four quarters of {item} with an 80% interval, as a trend indicator.",
        limitations="Uses each series' latest reported values (restatements included) rather than strict "
                    "as-first-reported values; structural breaks (M&A, spin-offs) are not modelled. Not guidance.",
        licences={"data": "SEC EDGAR, public domain"},
        save=lambda d: joblib.dump(forecaster, d / "model.joblib", compress=3), smoke_test=smoke,
        tables=results, gate_margin=0.0,
    )
    return finish_run(run, config)
