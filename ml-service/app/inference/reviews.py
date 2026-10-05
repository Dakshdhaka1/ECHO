"""M3 employee-review model: sentiment classifier + complaint themes + Employee Sentiment Index."""

from __future__ import annotations

import numpy as np
import pandas as pd

LABELS = ["negative", "neutral", "positive"]


def review_text(df: pd.DataFrame) -> pd.Series:
    return (df["headline"].fillna("") + ". Pros: " + df["pros"].fillna("") + ". Cons: " + df["cons"].fillna("")).str[:2000]


class ReviewModel:
    def __init__(self, classifier, theme_vectorizer, theme_model, theme_names: list[str]):
        self.classifier = classifier
        self.theme_vectorizer = theme_vectorizer
        self.theme_model = theme_model
        self.theme_names = theme_names

    def polarity(self, df: pd.DataFrame) -> np.ndarray:
        p = self.classifier.predict_proba(review_text(df))
        cls = list(self.classifier.classes_)
        return p[:, cls.index("positive")] - p[:, cls.index("negative")]

    def themes(self, df: pd.DataFrame) -> list[dict]:
        cons = df["cons"].fillna("")
        if cons.str.len().sum() == 0:
            return []
        W = self.theme_model.transform(self.theme_vectorizer.transform(cons))
        share = (W / np.maximum(W.sum(axis=1, keepdims=True), 1e-12)).mean(axis=0)
        order = np.argsort(-share)
        return [{"theme": self.theme_names[i], "share": float(share[i])} for i in order]

    def sentiment_index(self, df: pd.DataFrame, n_boot: int = 300, seed: int = 42) -> pd.DataFrame:
        """Company-quarter Employee Sentiment Index: mean polarity with a bootstrap 90% CI."""
        df = df.copy()
        df["polarity"] = self.polarity(df)
        df["quarter"] = pd.PeriodIndex(df["date_review"], freq="Q").astype(str)
        rng = np.random.default_rng(seed)
        rows = []
        for q, g in df.groupby("quarter"):
            vals = g["polarity"].to_numpy()
            boots = [rng.choice(vals, len(vals)).mean() for _ in range(n_boot)] if len(vals) > 1 else [vals.mean()]
            rows.append({"quarter": q, "index": float(vals.mean()), "ci90_low": float(np.quantile(boots, 0.05)),
                         "ci90_high": float(np.quantile(boots, 0.95)), "reviews": len(vals),
                         "mean_rating": float(g["overall_rating"].mean()) if "overall_rating" in g else None})
        return pd.DataFrame(rows)
