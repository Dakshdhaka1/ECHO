"""M1 news sentiment (ML_PIPELINE §4): baselines vs fine-tuned DistilRoBERTa, exported to ONNX.

    python -m pipelines.run news_sentiment
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.pipeline import FeatureUnion, Pipeline

from pipelines.common import RAW_DIR, SEED, manifest_hash, set_seed
from pipelines.evaluation.metrics import multiclass_metrics, plot_confusion, report_dir
from pipelines.ingestion.text_datasets import load_phrasebank, load_twitter
from pipelines.mlops import TrainingRun, finish_run

log = logging.getLogger("echo.training.sentiment")
LABELS = ["negative", "neutral", "positive"]
MODEL = "news_sentiment"


# ---------------------------------------------------------------- baselines
def vader_predict(texts: list[str]) -> list[str]:
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

    analyzer = SentimentIntensityAnalyzer()
    out = []
    for t in texts:
        c = analyzer.polarity_scores(t)["compound"]
        out.append("positive" if c >= 0.05 else "negative" if c <= -0.05 else "neutral")
    return out


def tfidf_pipeline(C: float) -> Pipeline:
    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, strip_accents="unicode")),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True)),
    ])
    return Pipeline([("features", features),
                     ("clf", LogisticRegression(C=C, max_iter=3000, class_weight="balanced", random_state=SEED))])


def train_tfidf(train: pd.DataFrame, val: pd.DataFrame, grid: list[float]) -> tuple[Pipeline, dict]:
    best, best_f1, scores = None, -1.0, {}
    for C in grid:
        pipe = tfidf_pipeline(C).fit(train["text"], train["label"])
        f1 = multiclass_metrics(val["label"], pipe.predict(val["text"]), LABELS)["macro_f1"]
        scores[C] = f1
        if f1 > best_f1:
            best, best_f1 = pipe, f1
    log.info("TF-IDF validation macro-F1 by C: %s", scores)
    return best, {"val_macro_f1_by_C": scores}


def finbert_predict(texts: list[str], model_name: str) -> list[str]:
    from transformers import pipeline

    clf = pipeline("text-classification", model=model_name, truncation=True, device=-1)
    return [r["label"].lower() for r in clf(texts, batch_size=64)]


# ---------------------------------------------------------------- transformer
def _encode(tokenizer, texts, labels, max_length):
    import torch

    enc = tokenizer(list(texts), truncation=True, max_length=max_length, padding="max_length", return_tensors="pt")
    y = torch.tensor([LABELS.index(label) for label in labels])
    return torch.utils.data.TensorDataset(enc["input_ids"], enc["attention_mask"], y)


def _predict_torch(model, tokenizer, texts, max_length, batch=128) -> np.ndarray:
    import torch

    model.eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), batch):
            enc = tokenizer(list(texts[i:i + batch]), truncation=True, max_length=max_length, padding=True,
                            return_tensors="pt")
            out.append(torch.softmax(model(**enc).logits, dim=-1).numpy())
    return np.vstack(out)


def finetune(train: pd.DataFrame, val: pd.DataFrame, cfg: dict):
    import torch
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        get_linear_schedule_with_warmup,
    )

    torch.set_num_threads(cfg["threads"])
    tokenizer = AutoTokenizer.from_pretrained(cfg["base_model"])
    model = AutoModelForSequenceClassification.from_pretrained(
        cfg["base_model"], num_labels=len(LABELS), id2label=dict(enumerate(LABELS)),
        label2id={label: i for i, label in enumerate(LABELS)})
    ds = _encode(tokenizer, train["text"], train["label"], cfg["max_length"])
    loader = torch.utils.data.DataLoader(ds, batch_size=cfg["batch_size"], shuffle=True,
                                         generator=torch.Generator().manual_seed(SEED))
    optim = torch.optim.AdamW(model.parameters(), lr=cfg["learning_rate"], weight_decay=cfg["weight_decay"])
    total = len(loader) * cfg["epochs"]
    sched = get_linear_schedule_with_warmup(optim, int(total * cfg["warmup_ratio"]), total)
    best_state, best_f1, history = None, -1.0, []
    for epoch in range(cfg["epochs"]):
        model.train()
        started, losses = time.monotonic(), []
        for step, (ids, mask, y) in enumerate(loader):
            loss = model(input_ids=ids, attention_mask=mask, labels=y).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optim.step()
            sched.step()
            optim.zero_grad()
            losses.append(loss.item())
            if step % 50 == 0:
                log.info("epoch %d step %d/%d loss %.4f", epoch + 1, step, len(loader), np.mean(losses[-50:]))
        probs = _predict_torch(model, tokenizer, val["text"].tolist(), cfg["max_length"])
        f1 = multiclass_metrics(val["label"], [LABELS[i] for i in probs.argmax(1)], LABELS)["macro_f1"]
        history.append({"epoch": epoch + 1, "train_loss": float(np.mean(losses)), "val_macro_f1": f1,
                        "seconds": round(time.monotonic() - started)})
        log.info("epoch %d done: %s", epoch + 1, history[-1])
        if f1 > best_f1:  # early stopping on validation macro-F1
            best_f1 = f1
            best_state = {k: v.detach().clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return model, tokenizer, history


def export_onnx(model, tokenizer, directory: Path, max_length: int) -> None:
    import torch
    from onnxruntime.quantization import QuantType, quantize_dynamic

    model.eval()
    dummy = tokenizer(["export example"], return_tensors="pt", padding="max_length", max_length=max_length)
    fp32 = directory / "model_fp32.onnx"
    args = (dummy["input_ids"], dummy["attention_mask"])
    kwargs = dict(input_names=["input_ids", "attention_mask"], output_names=["logits"], opset_version=17,
                  dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"},
                                "logits": {0: "batch"}})
    try:
        torch.onnx.export(model, args, str(fp32), dynamo=False, **kwargs)
    except TypeError:
        torch.onnx.export(model, args, str(fp32), **kwargs)
    quantize_dynamic(str(fp32), str(directory / "model.onnx"), weight_type=QuantType.QInt8)
    fp32.unlink()
    tokenizer.backend_tokenizer.save(str(directory / "tokenizer.json"))
    (directory / "labels.json").write_text(json.dumps({"labels": LABELS, "max_length": max_length,
                                                       "format": "onnx"}))


def _onnx_predict(directory: Path, texts: list[str]) -> np.ndarray:
    from app.inference.sentiment import SentimentModel

    return SentimentModel.load(directory).predict_proba(texts)


# ---------------------------------------------------------------- main
def train(config: dict) -> dict:
    set_seed()
    full = load_twitter("train")
    train_df, val_df = train_test_split(full, test_size=0.1, stratify=full["label"], random_state=SEED)
    test_tw, test_pb = load_twitter("valid"), load_phrasebank("AllAgree")
    out = report_dir(MODEL)
    results: dict[str, dict] = {}

    def evaluate(name: str, predict) -> None:
        results[name] = {"twitter_test": multiclass_metrics(test_tw["label"], predict(test_tw["text"].tolist()), LABELS)}
        if name != "finbert_offtheshelf":  # FinBERT was trained on PhraseBank: evaluating it there would leak
            results[name]["phrasebank"] = multiclass_metrics(test_pb["label"], predict(test_pb["text"].tolist()), LABELS)
        log.info("%s: %s", name, {k: round(v["macro_f1"], 4) for k, v in results[name].items()})

    evaluate("vader", vader_predict)
    tfidf, tfidf_info = train_tfidf(train_df, val_df, config["tfidf"]["C_grid"])
    evaluate("tfidf_logreg", lambda t: list(tfidf.predict(t)))
    val_scores = {"tfidf_logreg": max(tfidf_info["val_macro_f1_by_C"].values())}
    if config["finbert_baseline"]["enabled"]:
        evaluate("finbert_offtheshelf", lambda t: finbert_predict(t, config["finbert_baseline"]["model"]))

    candidate, history = "tfidf_logreg", []
    if config["transformer"]["enabled"]:
        tcfg = config["transformer"]
        model, tokenizer, history = finetune(train_df, val_df, tcfg)
        evaluate("distilroberta_finetuned",
                 lambda t: [LABELS[i] for i in _predict_torch(model, tokenizer, t, tcfg["max_length"]).argmax(1)])
        val_scores["distilroberta_finetuned"] = max(h["val_macro_f1"] for h in history)
        candidate = max(val_scores, key=val_scores.get)  # selection on validation only

    baselines = [b for b in ("vader", "tfidf_logreg") if b != candidate]
    best_base = max(baselines, key=lambda b: results[b]["phrasebank"]["macro_f1"])

    if candidate == "distilroberta_finetuned":
        tcfg = config["transformer"]

        def save(d: Path) -> None:
            export_onnx(model, tokenizer, d, tcfg["max_length"])
    else:
        def save(d: Path) -> None:
            import joblib
            joblib.dump(tfidf, d / "model.joblib", compress=3)
            (d / "labels.json").write_text(json.dumps({"labels": list(tfidf.classes_), "format": "sklearn"}))

    def smoke(d: Path) -> None:
        probs = _onnx_predict(d, ["Company beats earnings expectations", "Shares plunge after fraud probe"])
        assert probs.shape == (2, 3) and np.allclose(probs.sum(1), 1, atol=1e-4)
        assert probs[0, 2] > probs[0, 0] and probs[1, 0] > probs[1, 2], probs

    final_pred = None
    if candidate == "distilroberta_finetuned":
        final_pred = [LABELS[i] for i in _predict_torch(model, tokenizer, test_pb["text"].tolist(),
                                                        config["transformer"]["max_length"]).argmax(1)]
    else:
        final_pred = list(tfidf.predict(test_pb["text"]))
    cm_path = plot_confusion(test_pb["label"], final_pred, LABELS, out / "confusion_phrasebank.png",
                             f"{candidate} on Financial PhraseBank (AllAgree)")

    metrics = {"phrasebank_macro_f1": results[candidate]["phrasebank"]["macro_f1"],
               "phrasebank_accuracy": results[candidate]["phrasebank"]["accuracy"],
               "twitter_test_macro_f1": results[candidate]["twitter_test"]["macro_f1"],
               "twitter_test_accuracy": results[candidate]["twitter_test"]["accuracy"]}
    (out / "results.json").write_text(json.dumps({"results": results, "validation": val_scores,
                                                  "history": history}, indent=2))
    run = TrainingRun(
        model_name=MODEL, kind="ML", primary_metric="phrasebank_macro_f1", metrics=metrics,
        baseline={"name": best_base, "metrics": {"phrasebank_macro_f1": results[best_base]["phrasebank"]["macro_f1"],
                                                 "twitter_test_macro_f1": results[best_base]["twitter_test"]["macro_f1"]}},
        params={"selected": candidate, "validation_macro_f1": val_scores,
                **({"transformer": config["transformer"]} if candidate != "tfidf_logreg" else {})},
        data={"train": len(train_df), "validation": len(val_df), "test_twitter": len(test_tw),
              "test_phrasebank": len(test_pb), "manifest_sha256": manifest_hash(RAW_DIR / "MANIFEST.json"),
              "splits": config["data"]},
        intended_use="Sentiment of English financial-news headlines about a company (negative/neutral/positive). "
                     "Score = P(positive) - P(negative), aggregated over 90 days for the News pillar.",
        limitations="Headline-level only; misses sarcasm and context. Trained on short financial tweets/headlines, "
                    "so long or non-financial text is out of domain. English only.",
        licences={"train_data": "twitter-financial-news-sentiment, MIT",
                  "eval_data": "Financial PhraseBank, CC BY-NC-SA 3.0 (evaluation only)",
                  "base_model": "distilroberta-base, Apache-2.0" if candidate != "tfidf_logreg" else "n/a"},
        save=save, smoke_test=smoke, figures={"confusion_phrasebank": cm_path},
        tables={"comparison": results, "validation": val_scores, "training_history": history},
        gate_margin=config.get("gate_margin", 0.0),
    )
    return finish_run(run, config)
