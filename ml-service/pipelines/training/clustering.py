"""M4 peer clustering / company segmentation (ML_PIPELINE §4).

K-means vs Gaussian mixture on standardised financial ratios of the latest 10-K per company,
k chosen by silhouette; compared with the "sector only" baseline; stability measured as the
adjusted Rand index between a model fitted one year earlier and the current model.

    python -m pipelines.run peer_clusters
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402
from sklearn.decomposition import PCA  # noqa: E402
from sklearn.impute import SimpleImputer  # noqa: E402
from sklearn.metrics import adjusted_rand_score, davies_bouldin_score, silhouette_score  # noqa: E402
from sklearn.mixture import GaussianMixture  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.preprocessing import QuantileTransformer  # noqa: E402

from app.inference.segments import (  # noqa: E402
    SEGMENT_DESCRIPTIONS,
    SEGMENT_FEATURES,
    SegmentModel,
    name_clusters,
)
from pipelines.common import RAW_DIR, REPO_ROOT, SEED, manifest_hash, set_seed  # noqa: E402
from pipelines.evaluation.metrics import report_dir  # noqa: E402
from pipelines.mlops import TrainingRun, finish_run  # noqa: E402

log = logging.getLogger("echo.training.clustering")
MODEL = "peer_clusters"


def cross_section(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """Latest 10-K per company filed in `year`, with at least 6 of the segment features present."""
    snap = df[df["year"] == year].sort_values("as_of").groupby("cik").tail(1)
    snap = snap[snap[SEGMENT_FEATURES].notna().sum(axis=1) >= 6]
    return snap.set_index("cik")


def preprocess() -> Pipeline:
    # Rank-based normal scores make the heavy-tailed ratios comparable without outliers dominating k-means.
    return Pipeline([("impute", SimpleImputer(strategy="median")),
                     ("quantile", QuantileTransformer(output_distribution="normal", n_quantiles=500,
                                                      random_state=SEED))])


def train(config: dict) -> dict:
    set_seed()
    df = pd.read_parquet(REPO_ROOT / config["dataset"])
    current, previous = cross_section(df, config["year"]), cross_section(df, config["year"] - 1)
    X, X_prev = current[SEGMENT_FEATURES].astype(float), previous[SEGMENT_FEATURES].astype(float)
    X = X.replace([np.inf, -np.inf], np.nan)
    X_prev = X_prev.replace([np.inf, -np.inf], np.nan)
    pre = preprocess().fit(X)
    Z = pre.transform(X)
    rng = np.random.default_rng(SEED)
    sample = rng.choice(len(Z), size=min(len(Z), 4000), replace=False)  # silhouette is O(n^2)

    grid = {}
    for k in config["k_grid"]:
        km = KMeans(n_clusters=k, n_init=20, random_state=SEED).fit(Z)
        gm = GaussianMixture(n_components=k, covariance_type="full", random_state=SEED).fit(Z)
        gm_labels = gm.predict(Z)
        grid[k] = {
            "kmeans_silhouette": float(silhouette_score(Z[sample], km.labels_[sample])),
            "kmeans_davies_bouldin": float(davies_bouldin_score(Z, km.labels_)),
            "gmm_silhouette": float(silhouette_score(Z[sample], gm_labels[sample])) if len(set(gm_labels)) > 1 else -1,
            "gmm_bic": float(gm.bic(Z)),
        }
        log.info("k=%d %s", k, grid[k])
    best_k = max(grid, key=lambda k: grid[k]["kmeans_silhouette"])
    km = KMeans(n_clusters=best_k, n_init=20, random_state=SEED).fit(Z)
    sector_codes = pd.Categorical(current["sector"]).codes
    baseline_sil = float(silhouette_score(Z[sample], sector_codes[sample]))

    # Stability: fit the same procedure on the previous year and compare assignments of this year's companies.
    pre_prev = preprocess().fit(X_prev)
    km_prev = KMeans(n_clusters=best_k, n_init=20, random_state=SEED).fit(pre_prev.transform(X_prev))
    ari = float(adjusted_rand_score(km.labels_, km_prev.predict(pre_prev.transform(X))))

    centroids_z = pd.DataFrame(km.cluster_centers_, columns=SEGMENT_FEATURES)
    names = name_clusters(centroids_z)
    model = SegmentModel(pre, km, names, SEGMENT_FEATURES)
    assigned = model.assign(X)
    profile = X.assign(segment=assigned["segment"].to_numpy(), label=current["label"].to_numpy())
    summary = profile.groupby("segment").agg(
        companies=("net_margin", "size"), median_net_margin=("net_margin", "median"),
        median_revenue_yoy=("revenue_yoy", "median"), median_liabilities_assets=("liabilities_assets", "median"),
        median_current_ratio=("current_ratio", "median"), distress_rate_12m=("label", "mean")).round(4)
    log.info("segments:\n%s", summary)

    out = report_dir(MODEL)
    pca = PCA(n_components=2, random_state=SEED).fit(Z)
    P = pca.transform(Z)
    fig, ax = plt.subplots(figsize=(6, 4.5))
    for seg in sorted(set(assigned["segment"])):
        m = (assigned["segment"] == seg).to_numpy()
        ax.scatter(P[m, 0], P[m, 1], s=4, alpha=0.5, label=seg)
    ax.set(title=f"Company segments (k-means, k={best_k}) - PCA projection", xlabel="PC1", ylabel="PC2")
    ax.legend(markerscale=4, fontsize=8)
    fig.tight_layout()
    fig.savefig(out / "segments_pca.png", dpi=130)
    plt.close(fig)

    def smoke(d: Path) -> None:
        m = joblib.load(d / "model.joblib")
        res = m.assign(X.head(10))
        assert len(res) == 10 and set(res["segment"]) <= set(SEGMENT_DESCRIPTIONS)

    tables = {"k_grid": grid, "selected_k": best_k, "sector_only_silhouette": baseline_sil, "stability_ari": ari,
              "segment_profile": json.loads(summary.to_json(orient="index")), "names": names,
              "pca_explained_variance": pca.explained_variance_ratio_.round(3).tolist()}
    run = TrainingRun(
        model_name=MODEL, kind="ML", primary_metric="silhouette",
        metrics={"silhouette": grid[best_k]["kmeans_silhouette"], "davies_bouldin": grid[best_k]["kmeans_davies_bouldin"],
                 "stability_ari": ari, "k": best_k},
        baseline={"name": "sector_only", "metrics": {"silhouette": baseline_sil}},
        params={"algorithm": "kmeans", "k": best_k, "features": SEGMENT_FEATURES,
                "gmm_compared": True, "preprocessing": "median impute + quantile-normal transform"},
        data={"companies": len(X), "year": config["year"], "source": "latest 10-K per company (distress dataset)",
              "manifest_sha256": manifest_hash(RAW_DIR / "MANIFEST.json")},
        intended_use="Segment a company into Stable / Growth / Watchlist / High Risk by its financial profile, "
                     "for peer context in the dashboard.",
        limitations="Segments are descriptive groupings of accounting ratios, not ratings. Names are assigned by a "
                    "documented rule on cluster centroids. Silhouette scores for financial ratios are modest by nature.",
        licences={"data": "SEC EDGAR, public domain"},
        save=lambda d: joblib.dump(model, d / "model.joblib", compress=3), smoke_test=smoke,
        figures={"segments_pca": out / "segments_pca.png"}, tables=tables, gate_margin=0.0,
    )
    return finish_run(run, config)
