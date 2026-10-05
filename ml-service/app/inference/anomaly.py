"""Anomaly models (M5a market, M5b financial statements), shared by training and serving."""

from __future__ import annotations

import numpy as np
import pandas as pd

FINANCIAL_ANOMALY_FEATURES = ["bn_dsri", "bn_gmi", "bn_aqi", "bn_sgi", "bn_depi", "bn_sgai", "bn_lvgi", "bn_tata",
                              "revenue_yoy", "d_net_margin", "d_current_ratio"]
MARKET_ANOMALY_FEATURES = ["ret_z", "abs_ret_z", "volume_z", "range_z", "gap_z"]


def signed_log(x: pd.DataFrame) -> pd.DataFrame:
    return np.sign(x) * np.log1p(np.abs(x))


class IsolationScorer:
    """Isolation Forest + empirical-CDF calibration: score in [0, 1] = share of training rows less anomalous."""

    def __init__(self, preprocess, forest, features: list[str], train_scores: np.ndarray, transform: str = "none"):
        self.preprocess = preprocess
        self.forest = forest
        self.features = features
        self.train_scores = np.sort(train_scores)
        self.transform = transform

    def _matrix(self, X: pd.DataFrame) -> np.ndarray:
        X = pd.DataFrame(X).reindex(columns=self.features).astype(float).replace([np.inf, -np.inf], np.nan)
        if self.transform == "signed_log":
            X = signed_log(X)
        return self.preprocess.transform(X)

    def raw(self, X: pd.DataFrame) -> np.ndarray:
        return -self.forest.score_samples(self._matrix(X))  # higher = more anomalous

    def score(self, X: pd.DataFrame) -> np.ndarray:
        return np.searchsorted(self.train_scores, self.raw(X), side="right") / len(self.train_scores)

    def drivers(self, X: pd.DataFrame, top: int = 3) -> list[list[tuple[str, float]]]:
        """Largest absolute standardised deviations per row - a simple, honest 'why' for an anomaly."""
        Z = self._matrix(X)
        out = []
        for row in np.asarray(Z):
            order = np.argsort(-np.abs(row))[:top]
            out.append([(self.features[i], float(row[i])) for i in order])
        return out


def market_feature_frame(prices: pd.DataFrame, window: int = 60) -> pd.DataFrame:
    """Daily vectors for M5a from OHLCV: robust z-scores against a trailing window (no look-ahead)."""
    df = prices.sort_index()
    ret = np.log(df["close"]).diff()
    log_vol = np.log1p(df["volume"])
    rng = (df["high"] - df["low"]) / df["close"]
    gap = np.log(df["open"] / df["close"].shift(1))

    def robust_z(s: pd.Series) -> pd.Series:
        hist = s.shift(1).rolling(window, min_periods=window // 2)
        med = hist.median()
        mad = hist.apply(lambda w: np.median(np.abs(w - np.median(w))), raw=True) * 1.4826
        return (s - med) / mad.replace(0, np.nan)

    out = pd.DataFrame({
        "ret_z": robust_z(ret), "volume_z": robust_z(log_vol), "range_z": robust_z(rng), "gap_z": robust_z(gap),
    })
    out["abs_ret_z"] = out["ret_z"].abs()
    out["ret"] = ret
    return out.replace([np.inf, -np.inf], np.nan).dropna(subset=MARKET_ANOMALY_FEATURES)
