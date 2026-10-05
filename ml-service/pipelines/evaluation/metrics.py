"""Evaluation metrics and plots shared by the training modules (ML_PIPELINE §8)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.calibration import calibration_curve  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_recall_fscore_support,
    roc_auc_score,
    roc_curve,
)

from pipelines.common import REPORTS_DIR, SEED  # noqa: E402


def report_dir(model: str) -> Path:
    path = REPORTS_DIR / model
    path.mkdir(parents=True, exist_ok=True)
    return path


def multiclass_metrics(y_true, y_pred, labels: list[str]) -> dict:
    p, r, f, s = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    out = {"accuracy": accuracy_score(y_true, y_pred), "macro_f1": f1_score(y_true, y_pred, labels=labels,
                                                                          average="macro", zero_division=0)}
    for i, lab in enumerate(labels):
        out[f"{lab}_precision"], out[f"{lab}_recall"], out[f"{lab}_f1"] = float(p[i]), float(r[i]), float(f[i])
    return {k: float(v) for k, v in out.items()}


def binary_metrics(y_true, prob, threshold: float = 0.5) -> dict:
    y_true, prob = np.asarray(y_true), np.asarray(prob)
    pred = (prob >= threshold).astype(int)
    p, r, f, _ = precision_recall_fscore_support(y_true, pred, average="binary", zero_division=0)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    return {
        "roc_auc": float(roc_auc_score(y_true, prob)) if len(set(y_true)) > 1 else float("nan"),
        "pr_auc": float(average_precision_score(y_true, prob)) if len(set(y_true)) > 1 else float("nan"),
        "brier": float(brier_score_loss(y_true, np.clip(prob, 0, 1))) if np.all((prob >= 0) & (prob <= 1)) else float("nan"),
        "precision": float(p), "recall": float(r), "f1": float(f), "threshold": float(threshold),
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn), "positives": int(y_true.sum()), "n": int(len(y_true)),
    }


def bootstrap_ci(y_true, score, metric, n: int = 500, alpha: float = 0.1) -> tuple[float, float]:
    """Percentile bootstrap CI (stratified resampling keeps rare positives in every replicate)."""
    rng = np.random.default_rng(SEED)
    y_true, score = np.asarray(y_true), np.asarray(score)
    pos, neg = np.where(y_true == 1)[0], np.where(y_true == 0)[0]
    stats = []
    for _ in range(n):
        idx = np.concatenate([rng.choice(pos, len(pos)), rng.choice(neg, len(neg))])
        stats.append(metric(y_true[idx], score[idx]))
    return float(np.quantile(stats, alpha / 2)), float(np.quantile(stats, 1 - alpha / 2))


def best_f1_threshold(y_true, prob) -> float:
    precision, recall, thresholds = precision_recall_curve(y_true, prob)
    f1 = 2 * precision * recall / np.maximum(precision + recall, 1e-12)
    return float(thresholds[int(np.argmax(f1[:-1]))]) if len(thresholds) else 0.5


def plot_confusion(y_true, y_pred, labels: list[str], path: Path, title: str) -> Path:
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    fig, ax = plt.subplots(figsize=(4.2, 3.8))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)), labels, rotation=30)
    ax.set_yticks(range(len(labels)), labels)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, cm[i, j], ha="center", va="center", color="white" if cm[i, j] > cm.max() / 2 else "black")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def plot_curves(y_true, scores: dict[str, np.ndarray], path: Path, title: str) -> Path:
    """ROC and precision-recall curves for several models on the same test set."""
    fig, (a, b) = plt.subplots(1, 2, figsize=(9, 3.8))
    for name, s in scores.items():
        fpr, tpr, _ = roc_curve(y_true, s)
        a.plot(fpr, tpr, label=f"{name} (AUC {roc_auc_score(y_true, s):.3f})")
        prec, rec, _ = precision_recall_curve(y_true, s)
        b.plot(rec, prec, label=f"{name} (AP {average_precision_score(y_true, s):.3f})")
    a.plot([0, 1], [0, 1], "k--", lw=0.8)
    a.set(xlabel="False positive rate", ylabel="True positive rate", title="ROC")
    b.axhline(np.mean(y_true), color="k", ls="--", lw=0.8)
    b.set(xlabel="Recall", ylabel="Precision", title="Precision-recall")
    a.legend(fontsize=7)
    b.legend(fontsize=7)
    fig.suptitle(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def plot_calibration(y_true, probs: dict[str, np.ndarray], path: Path, bins: int = 10) -> Path:
    fig, ax = plt.subplots(figsize=(4.5, 4))
    for name, p in probs.items():
        frac, mean = calibration_curve(y_true, p, n_bins=bins, strategy="quantile")
        ax.plot(mean, frac, marker="o", label=name)
    ax.plot([0, 1], [0, 1], "k--", lw=0.8)
    ax.set(xlabel="Mean predicted probability", ylabel="Observed frequency", title="Calibration (quantile bins)",
           xscale="log", yscale="log")
    ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
