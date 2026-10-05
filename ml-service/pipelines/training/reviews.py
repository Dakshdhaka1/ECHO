"""M3 employee-review sentiment + themes (ML_PIPELINE §4).

Requires the Kaggle "Glassdoor Job Reviews" CSV at data/raw/reviews/glassdoor_reviews.csv, downloaded
by the user with their own Kaggle account (it is never scraped or committed). Split is grouped by
company: firms in the test set never appear in training.

    python -m pipelines.run review_sentiment
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import GroupShuffleSplit

from app.inference.reviews import LABELS, ReviewModel, review_text
from pipelines.common import RAW_DIR, SEED, set_seed, update_manifest
from pipelines.evaluation.metrics import multiclass_metrics, plot_confusion, report_dir
from pipelines.mlops import TrainingRun, finish_run
from pipelines.training.sentiment import tfidf_pipeline, vader_predict

log = logging.getLogger("echo.training.reviews")
MODEL = "review_sentiment"
CSV = RAW_DIR / "reviews" / "glassdoor_reviews.csv"
# Review boilerplate that otherwise forms filler topics ("cons / working / don", "company / good / time")
REVIEW_STOPWORDS = ["cons", "pros", "con", "pro", "don", "didn", "doesn", "isn", "good", "great", "really", "think",
                    "company", "work", "working", "job", "time", "people", "lot", "just", "like", "things", "thing",
                    "moment", "nothing", "none", "say", "bad", "way", "place", "able", "make", "know", "want", "get",
                    "got", "bit", "sometimes", "quite", "lots", "everything", "anything", "far", "come", "dont", "cant"]

THEME_KEYWORDS = {
    "pay & benefits": {"pay", "salary", "benefits", "compensation", "bonus", "raise", "wage"},
    "management": {"management", "manager", "managers", "leadership", "senior", "micromanagement"},
    "work-life balance": {"hours", "balance", "life", "overtime", "stress", "weekends", "shifts"},
    "job security & layoffs": {"layoffs", "security", "restructuring", "cuts", "layoff", "redundancy"},
    "career growth": {"career", "promotion", "growth", "progression", "advancement", "training"},
    "culture & politics": {"culture", "politics", "toxic", "favoritism", "communication", "bureaucracy"},
    "workload & staffing": {"understaffed", "workload", "staff", "busy", "pressure", "targets"},
}


def rating_label(r: float) -> str:
    return "negative" if r <= 2 else "neutral" if r == 3 else "positive"


def name_topics(vectorizer, nmf, top: int = 12) -> list[str]:
    vocab = np.array(vectorizer.get_feature_names_out())
    names, used = [], set()
    for comp in nmf.components_:
        words = set(vocab[np.argsort(-comp)[:top]])
        scored = sorted(THEME_KEYWORDS, key=lambda t: -len(words & THEME_KEYWORDS[t]))
        best = next((t for t in scored if t not in used and words & THEME_KEYWORDS[t]), None)
        label = best or " / ".join(vocab[np.argsort(-comp)[:3]])
        used.add(label)
        names.append(label)
    return names


def train(config: dict) -> dict:
    if not CSV.exists():
        raise FileNotFoundError(f"{CSV} - download the Kaggle 'Glassdoor Job Reviews' dataset (see README)")
    set_seed()
    update_manifest(RAW_DIR / "MANIFEST.json", CSV, "https://www.kaggle.com/datasets/davidgauthier/glassdoor-job-reviews")
    df = pd.read_csv(CSV, low_memory=False)
    df = df.dropna(subset=["overall_rating", "firm"])
    df["date_review"] = pd.to_datetime(df["date_review"], errors="coerce")
    df = df.dropna(subset=["date_review"])
    if len(df) > config["max_reviews"]:
        df = df.sample(config["max_reviews"], random_state=SEED)
    df["label"] = df["overall_rating"].map(rating_label)
    gss = GroupShuffleSplit(n_splits=1, test_size=0.3, random_state=SEED)
    tr_idx, rest_idx = next(gss.split(df, groups=df["firm"]))
    rest = df.iloc[rest_idx]
    va_idx, te_idx = next(GroupShuffleSplit(n_splits=1, test_size=0.5, random_state=SEED).split(rest, groups=rest["firm"]))
    tr, va, te = df.iloc[tr_idx], rest.iloc[va_idx], rest.iloc[te_idx]
    log.info("reviews train/val/test = %d/%d/%d (firms %d/%d/%d)", len(tr), len(va), len(te),
             tr["firm"].nunique(), va["firm"].nunique(), te["firm"].nunique())

    best, best_f1 = None, -1.0
    for C in config["C_grid"]:
        pipe = tfidf_pipeline(C).fit(review_text(tr), tr["label"])
        f1 = multiclass_metrics(va["label"], pipe.predict(review_text(va)), LABELS)["macro_f1"]
        log.info("C=%s val macro-F1 %.4f", C, f1)
        if f1 > best_f1:
            best, best_f1 = pipe, f1
    pred = best.predict(review_text(te))
    model_metrics = multiclass_metrics(te["label"], pred, LABELS)
    vader_metrics = multiclass_metrics(te["label"], vader_predict(review_text(te).tolist()), LABELS)

    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

    vec = TfidfVectorizer(max_features=8000, stop_words=sorted(ENGLISH_STOP_WORDS.union(REVIEW_STOPWORDS)),
                          min_df=20, max_df=0.4)
    nmf = NMF(n_components=config["themes"], random_state=SEED, init="nndsvda", max_iter=400)
    nmf.fit(vec.fit_transform(tr["cons"].fillna("").map(lambda s: re.sub(r"\s+", " ", s))))
    names = name_topics(vec, nmf)
    model = ReviewModel(best, vec, nmf, names)

    esi = []
    for firm, g in te.groupby("firm"):
        if len(g) >= 30:
            idx = model.sentiment_index(g)
            esi.append(idx[idx["reviews"] >= 10])
    esi = pd.concat(esi)
    corr = {"pearson": float(pearsonr(esi["index"], esi["mean_rating"])[0]),
            "spearman": float(spearmanr(esi["index"], esi["mean_rating"])[0]), "company_quarters": len(esi)}
    log.info("model %s | vader %s | ESI correlation %s", model_metrics["macro_f1"], vader_metrics["macro_f1"], corr)
    out = report_dir(MODEL)
    cm = plot_confusion(te["label"], pred, LABELS, out / "confusion_test.png", "Review sentiment - company-held-out test")

    def smoke(d: Path) -> None:
        m = joblib.load(d / "model.joblib")
        pol = m.polarity(te.head(5))
        assert pol.shape == (5,) and np.all(np.abs(pol) <= 1)
        assert m.themes(te.head(50))

    run = TrainingRun(
        model_name=MODEL, kind="ML", primary_metric="macro_f1",
        metrics={**model_metrics, "esi_pearson": corr["pearson"], "esi_spearman": corr["spearman"]},
        baseline={"name": "vader", "metrics": vader_metrics},
        params={"model": "tfidf_logreg", "themes": names, "C_grid": config["C_grid"]},
        data={"reviews": {"train": len(tr), "validation": len(va), "test": len(te)}, "split": "grouped by firm",
              "label": "overall_rating <=2 negative, 3 neutral, >=4 positive"},
        intended_use="Score employee reviews and aggregate them into a company-quarter Employee Sentiment Index "
                     "with themes of complaints, for the Workforce pillar.",
        limitations="Dataset ends around 2021, so the index is historical for most companies. Reviews are "
                    "self-selected and not a random sample of employees.",
        licences={"data": "Kaggle Glassdoor Job Reviews - verify licence (L2); academic use"},
        save=lambda d: joblib.dump(model, d / "model.joblib", compress=3), smoke_test=smoke,
        figures={"confusion": cm}, tables={"model": model_metrics, "vader": vader_metrics, "esi_correlation": corr,
                                           "themes": names},
    )
    return finish_run(run, config)
