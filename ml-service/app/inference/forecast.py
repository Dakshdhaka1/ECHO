"""M6 fundamentals forecaster: global LightGBM (direct multi-horizon) + split-conformal intervals."""

from __future__ import annotations

import numpy as np
import pandas as pd

N_LAGS = 8
HORIZONS = (1, 2, 3, 4)
FEATURES = [f"lag_{k}" for k in range(N_LAGS)] + ["yoy_ratio", "growth_4q", "volatility", "quarter", "horizon",
                                                   "log_scale"]


def regular_quarters(s: pd.Series) -> pd.Series:
    """Keep the most recent run of consecutive quarters (gaps of 75-105 days)."""
    s = s.dropna().sort_index()
    if len(s) < 2:
        return s
    gaps = np.diff(s.index.values).astype("timedelta64[D]").astype(int)
    breaks = np.where((gaps < 75) | (gaps > 105))[0]
    start = breaks[-1] + 1 if len(breaks) else 0
    return s.iloc[start:]


def origin_features(values: np.ndarray, end: pd.Timestamp, horizon: int) -> dict | None:
    """Features at an origin whose last observed value is values[-1] (needs >= N_LAGS values)."""
    if len(values) < N_LAGS:
        return None
    last = values[-N_LAGS:]
    scale = float(np.mean(np.abs(last[-4:])))
    if not np.isfinite(scale) or scale <= 0:
        return None
    feats = {f"lag_{k}": float(last[-1 - k] / scale) for k in range(N_LAGS)}
    feats["yoy_ratio"] = float(last[-1] / last[-5]) if last[-5] != 0 else np.nan
    prev_year = np.sum(last[-8:-4])
    feats["growth_4q"] = float(np.sum(last[-4:]) / prev_year - 1) if prev_year > 0 else np.nan
    feats["volatility"] = float(np.std(np.diff(last) / scale))
    feats["quarter"] = int(((end + pd.Timedelta(days=91 * horizon)).month - 1) // 3 + 1)
    feats["horizon"] = horizon
    feats["log_scale"] = float(np.log10(scale))
    return feats | {"_scale": scale}


class ForecastModel:
    def __init__(self, model, residual_quantiles: dict[int, tuple[float, float]], item: str):
        self.model = model
        self.residual_quantiles = residual_quantiles  # horizon -> (q10, q90) of (y - yhat) / scale
        self.item = item

    def predict(self, series: pd.Series) -> list[dict]:
        s = regular_quarters(series)
        if len(s) < N_LAGS:
            return []
        values, end = s.to_numpy(dtype=float), s.index[-1]
        rows, scales = [], []
        for h in HORIZONS:
            f = origin_features(values, end, h)
            if f is None:
                return []
            scales.append(f.pop("_scale"))
            rows.append(f)
        X = pd.DataFrame(rows)[FEATURES]
        pred = self.model.predict(X)
        out = []
        for h, p, scale in zip(HORIZONS, pred, scales, strict=True):
            q10, q90 = self.residual_quantiles[h]
            out.append({"horizon": h, "period_end": (end + pd.Timedelta(days=91 * h)).date().isoformat(),
                        "p10": float((p + q10) * scale), "p50": float(p * scale), "p90": float((p + q90) * scale)})
        return out
