"""M7 distress probability (12-month) - ML_PIPELINE §4.

    python -m pipelines.run distress
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.inference.tabular import DistressModel, PlattCalibrator, Winsorizer, risk_band
from pipelines.common import RAW_DIR, REPO_ROOT, SEED, manifest_hash, set_seed
from pipelines.evaluation.metrics import (
    best_f1_threshold,
    binary_metrics,
    bootstrap_ci,
    plot_calibration,
    plot_confusion,
    plot_curves,
    report_dir,
)
from pipelines.features.distress_dataset import FEATURE_COLUMNS
from pipelines.mlops import TrainingRun, finish_run
from pipelines.monitoring.drift import reference_histogram

log = logging.getLogger("echo.training.distress")
MODEL = "distress"
optuna.logging.set_verbosity(optuna.logging.WARNING)


def make_pipeline(algo: str, params: dict, pos_weight: float, winsor: tuple[float, float]) -> Pipeline:
    w = ("winsor", Winsorizer(*winsor))
    if algo == "logistic_regression":
        return Pipeline([w, ("impute", SimpleImputer(strategy="median", add_indicator=True)),
                         ("scale", StandardScaler()),
                         ("clf", LogisticRegression(C=params.get("C", 0.1), class_weight="balanced", max_iter=5000))])
    if algo == "random_forest":
        return Pipeline([w, ("clf", RandomForestClassifier(
            n_estimators=500, min_samples_leaf=params.get("min_samples_leaf", 20), max_features="sqrt",
            class_weight="balanced_subsample", n_jobs=-1, random_state=SEED))])
    if algo == "xgboost":
        return Pipeline([w, ("clf", xgb.XGBClassifier(
            n_estimators=params.get("n_estimators", 400), max_depth=params.get("max_depth", 4),
            learning_rate=params.get("learning_rate", 0.03), subsample=0.8, colsample_bytree=0.8,
            min_child_weight=params.get("min_child_weight", 5), scale_pos_weight=pos_weight,
            eval_metric="aucpr", n_jobs=-1, random_state=SEED))])
    return Pipeline([w, ("clf", lgb.LGBMClassifier(
        n_estimators=params.get("n_estimators", 400), learning_rate=params.get("learning_rate", 0.03),
        num_leaves=params.get("num_leaves", 15), min_child_samples=params.get("min_child_samples", 50),
        subsample=params.get("subsample", 0.8), subsample_freq=1,
        colsample_bytree=params.get("colsample_bytree", 0.8), reg_lambda=params.get("reg_lambda", 1.0),
        scale_pos_weight=params.get("scale_pos_weight", pos_weight), random_state=SEED, n_jobs=-1, verbose=-1))])


def tune_lightgbm(X_tr, y_tr, X_va, y_va, pos_weight, winsor, trials: int) -> dict:
    def objective(trial: optuna.Trial) -> float:
        params = {
            "n_estimators": trial.suggest_int("n_estimators", 150, 800, step=50),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 7, 63),
            "min_child_samples": trial.suggest_int("min_child_samples", 20, 300, log=True),
            "subsample": trial.suggest_float("subsample", 0.6, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10, log=True),
            "scale_pos_weight": trial.suggest_float("scale_pos_weight", 1.0, pos_weight, log=True),
        }
        pipe = make_pipeline("lightgbm", params, pos_weight, winsor).fit(X_tr, y_tr)
        return average_precision_score(y_va, pipe.predict_proba(X_va)[:, 1])

    study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=SEED))
    study.optimize(objective, n_trials=trials)
    log.info("Optuna best validation PR-AUC %.4f with %s", study.best_value, study.best_params)
    return study.best_params


def _split(df: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    s = cfg["split"]
    in_range = lambda r: df["year"].between(*r)  # noqa: E731
    return df[in_range(s["train"])], df[in_range(s["validation"])], df[in_range(s["test"])]


def shap_summary(model: DistressModel, X: pd.DataFrame, path: Path) -> tuple[Path, dict]:
    import matplotlib.pyplot as plt
    import shap

    contrib, _ = model.contributions(X)
    importance = pd.Series(np.abs(contrib).mean(axis=0), index=model.features).sort_values(ascending=False)
    shap.summary_plot(contrib, X[model.features], show=False, max_display=15, plot_size=(8, 6))
    plt.title("SHAP values (log-odds) on the test set", fontsize=10)
    plt.tight_layout()
    plt.savefig(path, dpi=130)
    plt.close("all")
    return path, importance.round(5).to_dict()


def train(config: dict) -> dict:
    set_seed()
    df = pd.read_parquet(REPO_ROOT / config["dataset"])
    tr, va, te = _split(df, config)
    features = FEATURE_COLUMNS
    X_tr, X_va, X_te = tr[features], va[features], te[features]
    y_tr, y_va, y_te = tr["label"].to_numpy(), va["label"].to_numpy(), te["label"].to_numpy()
    pos_weight = float((y_tr == 0).sum() / max(1, (y_tr == 1).sum()))
    winsor = tuple(config["winsorize"])
    log.info("rows train/val/test = %d/%d/%d; positives = %d/%d/%d", len(tr), len(va), len(te),
             y_tr.sum(), y_va.sum(), y_te.sum())
    out = report_dir(MODEL)

    # ---- candidates, selected on validation PR-AUC
    tuned = tune_lightgbm(X_tr, y_tr, X_va, y_va, pos_weight, winsor, config["optuna_trials"])
    params = {"lightgbm": tuned, "logistic_regression": {"C": 0.1}, "random_forest": {}, "xgboost": {}}
    fitted, val_scores = {}, {}
    for algo in config["candidates"]:
        pipe = make_pipeline(algo, params[algo], pos_weight, winsor).fit(X_tr, y_tr)
        fitted[algo] = pipe
        p = pipe.predict_proba(X_va)[:, 1]
        val_scores[algo] = {"pr_auc": float(average_precision_score(y_va, p)), "roc_auc": float(roc_auc_score(y_va, p))}
        log.info("validation %s: %s", algo, val_scores[algo])
    best = max(val_scores, key=lambda a: val_scores[a]["pr_auc"])

    # ---- calibration on validation. Platt (sigmoid on the log-odds) is strictly monotone, so it keeps the
    # ranking (ROC/PR) intact; isotonic is fitted too and compared on the calibration plot and Brier score.
    raw_va = fitted[best].predict_proba(X_va)[:, 1]
    calibrator = PlattCalibrator().fit(raw_va, y_va)
    isotonic = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(raw_va, y_va)
    model = DistressModel(fitted[best], calibrator, features, best, threshold=0.5)
    model.threshold = best_f1_threshold(y_va, model.predict_proba(X_va))

    # ---- test set, used once
    test_scores = {a: fitted[a].predict_proba(X_te)[:, 1] for a in fitted}
    prob_te = model.predict_proba(X_te)
    altman = -te["altman_z2"].fillna(te["altman_z2"].median()).to_numpy()   # lower Z'' = riskier
    ohlson = te["ohlson_o"].fillna(te["ohlson_o"].median()).to_numpy()      # higher O = riskier
    comparison = {}
    for name, score in {**test_scores, "altman_z2_baseline": altman, "ohlson_o_baseline": ohlson}.items():
        comparison[name] = {"roc_auc": float(roc_auc_score(y_te, score)),
                            "pr_auc": float(average_precision_score(y_te, score))}
    metrics = binary_metrics(y_te, prob_te, model.threshold)
    metrics["brier_isotonic"] = float(binary_metrics(y_te, isotonic.predict(test_scores[best]))["brier"])
    metrics["brier_raw"] = float(binary_metrics(y_te, test_scores[best])["brier"])
    metrics["pr_auc_ci90"] = bootstrap_ci(y_te, prob_te, average_precision_score)
    metrics["roc_auc_ci90"] = bootstrap_ci(y_te, prob_te, roc_auc_score)
    best_baseline = max(["altman_z2_baseline", "ohlson_o_baseline"], key=lambda b: comparison[b]["pr_auc"])
    log.info("test %s: %s", best, {k: metrics[k] for k in ("roc_auc", "pr_auc", "brier", "f1")})
    log.info("test comparison: %s", comparison)

    # ---- ablation: drop one feature group at a time (LightGBM with tuned params, validation + test PR-AUC)
    ablation = {}
    for group, cols in config["feature_groups"].items():
        keep = [c for c in features if c not in cols]
        pipe = make_pipeline("lightgbm", tuned, pos_weight, winsor).fit(X_tr[keep], y_tr)
        ablation[group] = {"val_pr_auc": float(average_precision_score(y_va, pipe.predict_proba(X_va[keep])[:, 1])),
                           "test_pr_auc": float(average_precision_score(y_te, pipe.predict_proba(X_te[keep])[:, 1]))}
    log.info("ablation: %s", ablation)

    # ---- figures
    figures = {
        "roc_pr_curves": plot_curves(y_te, {**{a: s for a, s in test_scores.items()},
                                            "Altman Z''": altman, "Ohlson O": ohlson},
                                     out / "roc_pr_test.png", "Distress (12-month) - test set 2022-2024"),
        "calibration": plot_calibration(y_te, {f"{best} (Platt)": prob_te,
                                               f"{best} (isotonic)": isotonic.predict(test_scores[best]),
                                               f"{best} (raw, class-weighted)": test_scores[best]},
                                        out / "calibration_test.png"),
        "confusion": plot_confusion(y_te, (prob_te >= model.threshold).astype(int), [0, 1],
                                    out / "confusion_test.png", f"Test confusion matrix (threshold {model.threshold:.3f})"),
    }
    shap_path, importance = shap_summary(model, X_te, out / "shap_summary_test.png")
    figures["shap_summary"] = shap_path
    band_counts = pd.Series([risk_band(p) for p in prob_te]).value_counts().to_dict()
    band_rates = {b: float(y_te[np.array([risk_band(p) for p in prob_te]) == b].mean())
                  for b in band_counts}

    def smoke(d: Path) -> None:
        m = joblib.load(d / "model.joblib")
        p = m.predict_proba(X_te.head(20))
        contrib, base = m.contributions(X_te.head(5))
        assert p.shape == (20,) and np.all((p >= 0) & (p <= 1))
        assert contrib.shape == (5, len(features)) and base.shape == (5,)

    def save(d: Path) -> None:
        joblib.dump(model, d / "model.joblib", compress=3)
        reference = {"features": {f: h for f in features if (h := reference_histogram(X_tr[f])) is not None},
                     "prediction": reference_histogram(pd.Series(model.predict_proba(X_va)))}
        (d / "reference.json").write_text(json.dumps(reference))

    tables = {"validation": val_scores, "test_comparison": comparison, "ablation_drop_group": ablation,
              "shap_mean_abs": importance, "risk_bands_test": {"counts": band_counts, "observed_rate": band_rates},
              "optuna_best_params": tuned}
    (out / "results.json").write_text(json.dumps(tables, indent=2, default=float))
    run = TrainingRun(
        model_name=MODEL, kind="ML", primary_metric="pr_auc",
        metrics={k: v for k, v in metrics.items() if isinstance(v, (int, float))},
        baseline={"name": best_baseline, "metrics": comparison[best_baseline]},
        params={"algorithm": best, "threshold": model.threshold, "hyperparameters": params[best],
                "features": features, "calibration": "Platt (sigmoid) on validation"},
        data={"rows": {"train": len(tr), "validation": len(va), "test": len(te)},
              "positives": {"train": int(y_tr.sum()), "validation": int(y_va.sum()), "test": int(y_te.sum())},
              "split": config["split"], "source": "SEC companyfacts.zip + submissions.zip (8-K Item 1.03 labels)",
              "manifest_sha256": manifest_hash(RAW_DIR / "MANIFEST.json"),
              "metrics_ci90": {"pr_auc": metrics["pr_auc_ci90"], "roc_auc": metrics["roc_auc_ci90"]}},
        intended_use="Estimated probability that a US-listed non-financial company files for bankruptcy "
                     "(8-K Item 1.03) within 12 months, from point-in-time public accounting data and SEC events.",
        limitations="Accounting + SEC-event features only (no market prices for delisted companies). Rare-event "
                    "model: probabilities are calibrated on 2020-2021 and can drift with the credit cycle. "
                    "Bankruptcies of companies that stopped filing before the event are not captured. "
                    "Not investment advice.",
        licences={"data": "SEC EDGAR, public domain"},
        save=save, smoke_test=smoke,
        figures=figures, tables=tables, gate_margin=config.get("gate_margin", 0.0),
    )
    return finish_run(run, config)
