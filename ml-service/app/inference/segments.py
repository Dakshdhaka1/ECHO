"""M4 company segmentation model (shared by training and serving)."""

from __future__ import annotations

import numpy as np
import pandas as pd

SEGMENT_FEATURES = ["net_margin", "roa", "revenue_yoy", "liabilities_assets", "current_ratio", "fcf_margin",
                    "log_assets", "ocf_liabilities"]

SEGMENT_DESCRIPTIONS = {
    "Stable": "Profitable, cash-generative and moderately levered relative to the market.",
    "Growth": "Revenue growing much faster than the market; profitability secondary.",
    "Watchlist": "Mixed profile: weaker margins or liquidity than Stable companies, without acute distress.",
    "High Risk": "Losses, cash burn and/or high leverage - the profile most associated with distress.",
}


def name_clusters(centroids_z: pd.DataFrame) -> dict[int, str]:
    """Name clusters from their standardised centroids (documented rule, Kind = Rule on top of ML)."""
    risk = (centroids_z["liabilities_assets"] - centroids_z["current_ratio"] - centroids_z["fcf_margin"]
            - centroids_z["net_margin"] - centroids_z["ocf_liabilities"])
    growth = centroids_z["revenue_yoy"]
    profit = centroids_z["net_margin"] + centroids_z["roa"] + centroids_z["fcf_margin"]
    names: dict[int, str] = {}
    remaining = list(centroids_z.index)
    for label, score in (("High Risk", risk), ("Growth", growth), ("Stable", profit)):
        best = max(remaining, key=lambda c: score[c])
        names[best] = label
        remaining.remove(best)
    for c in remaining:
        names[c] = "Watchlist"
    return names


class SegmentModel:
    def __init__(self, preprocess, kmeans, names: dict[int, str], features: list[str]):
        self.preprocess = preprocess
        self.kmeans = kmeans
        self.names = names
        self.features = features

    def assign(self, X: pd.DataFrame) -> pd.DataFrame:
        X = pd.DataFrame(X).reindex(columns=self.features).astype(float).replace([np.inf, -np.inf], np.nan)
        Z = self.preprocess.transform(X)
        dist = self.kmeans.transform(Z)
        labels = dist.argmin(axis=1)
        # Soft membership from distances (softmax of negative squared distance) as a confidence measure.
        logits = -(dist ** 2)
        w = np.exp(logits - logits.max(axis=1, keepdims=True))
        w /= w.sum(axis=1, keepdims=True)
        return pd.DataFrame({
            "cluster": labels,
            "segment": [self.names[int(c)] for c in labels],
            "membership": w[np.arange(len(labels)), labels],
        }, index=X.index)
