"""Model classes shared by training and serving (pickled with joblib, so they must live in `app`)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin


class Winsorizer(BaseEstimator, TransformerMixin):
    """Clip each column to quantiles fitted on the training data only (ML_PIPELINE §5)."""

    def __init__(self, lower: float = 0.01, upper: float = 0.99):
        self.lower = lower
        self.upper = upper

    def fit(self, X, y=None):
        X = pd.DataFrame(X)
        self.columns_ = list(X.columns)
        self.lo_ = X.quantile(self.lower).to_numpy()
        self.hi_ = X.quantile(self.upper).to_numpy()
        return self

    def transform(self, X):
        X = pd.DataFrame(X, columns=self.columns_)
        return X.clip(self.lo_, self.hi_, axis=1)

    def get_feature_names_out(self, input_features=None):
        return np.array(self.columns_)


class PlattCalibrator:
    """Platt scaling: logistic regression on the model's log-odds (monotone, so ranking is preserved)."""

    def fit(self, scores, y):
        from sklearn.linear_model import LogisticRegression

        z = self._logit(np.asarray(scores, dtype=float)).reshape(-1, 1)
        self.lr_ = LogisticRegression(C=1e6, max_iter=1000).fit(z, np.asarray(y))
        return self

    @staticmethod
    def _logit(p: np.ndarray) -> np.ndarray:
        p = np.clip(p, 1e-9, 1 - 1e-9)
        return np.log(p / (1 - p))

    def predict(self, scores) -> np.ndarray:
        z = self._logit(np.asarray(scores, dtype=float)).reshape(-1, 1)
        return self.lr_.predict_proba(z)[:, 1]


RISK_BANDS = [(0.01, "LOW"), (0.03, "MODERATE"), (0.10, "ELEVATED"), (1.01, "HIGH")]


def risk_band(probability: float) -> str:
    for upper, band in RISK_BANDS:
        if probability < upper:
            return band
    return "HIGH"


class DistressModel:
    """Calibrated 12-month distress probability + per-feature contributions (log-odds, SHAP)."""

    def __init__(self, pipeline, calibrator, features: list[str], algorithm: str, threshold: float):
        self.pipeline = pipeline
        self.calibrator = calibrator
        self.features = features
        self.algorithm = algorithm
        self.threshold = threshold

    def _frame(self, X) -> pd.DataFrame:
        X = pd.DataFrame(X)
        return X.reindex(columns=self.features).astype(float).replace([np.inf, -np.inf], np.nan)

    def raw_score(self, X) -> np.ndarray:
        return self.pipeline.predict_proba(self._frame(X))[:, 1]

    def predict_proba(self, X) -> np.ndarray:
        return np.clip(self.calibrator.predict(self.raw_score(X)), 0.0, 1.0)

    def contributions(self, X) -> tuple[np.ndarray, np.ndarray]:
        """(contributions[n, n_features], base_value[n]) in the model's margin (log-odds) space."""
        X = self._frame(X)
        steps = self.pipeline.steps
        transformed = X
        for _, step in steps[:-1]:
            transformed = step.transform(transformed)
        est = steps[-1][1]
        if self.algorithm == "lightgbm":
            contrib = est.predict(transformed, pred_contrib=True)
            return contrib[:, :-1][:, : len(self.features)], contrib[:, -1]
        if self.algorithm == "xgboost":
            import xgboost as xgb

            contrib = est.get_booster().predict(xgb.DMatrix(np.asarray(transformed, dtype=float)), pred_contribs=True)
            return contrib[:, :-1], contrib[:, -1]
        if self.algorithm == "logistic_regression":
            # Linear model: exact contribution = coef * (x - training mean) in standardised space.
            coef = est.coef_[0]
            Z = np.asarray(transformed, dtype=float)
            n = len(self.features)
            contrib = Z[:, :n] * coef[:n]
            base = np.full(len(Z), est.intercept_[0]) + (Z[:, n:] * coef[n:]).sum(axis=1)
            return contrib, base
        import shap  # random forest

        explainer = shap.TreeExplainer(est)
        values = explainer.shap_values(np.asarray(transformed, dtype=float))
        values = values[1] if isinstance(values, list) else values[..., 1] if values.ndim == 3 else values
        base = explainer.expected_value
        base = base[1] if np.ndim(base) else base
        return values, np.full(len(X), base)
