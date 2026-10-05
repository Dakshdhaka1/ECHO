"""Download the sentiment datasets (ML_PIPELINE §3) into data/raw/text with a manifest.

* twitter-financial-news-sentiment (MIT, Hugging Face `zeroshot`) - training + validation
* Financial PhraseBank v1.0 (CC BY-NC-SA 3.0) - evaluation only, never used for training

    python -m pipelines.ingestion.text_datasets
"""

from __future__ import annotations

import zipfile

import pandas as pd

from pipelines.common import RAW_DIR, download, setup_logging

TEXT_DIR = RAW_DIR / "text"
MANIFEST = RAW_DIR / "MANIFEST.json"
HF = "https://huggingface.co/datasets/{repo}/resolve/main/{file}"
FILES = {
    "twitter_fin_train.csv": HF.format(repo="zeroshot/twitter-financial-news-sentiment", file="sent_train.csv"),
    "twitter_fin_valid.csv": HF.format(repo="zeroshot/twitter-financial-news-sentiment", file="sent_valid.csv"),
    "FinancialPhraseBank-v1.0.zip": HF.format(repo="takala/financial_phrasebank",
                                              file="data/FinancialPhraseBank-v1.0.zip"),
}
LABELS = ["negative", "neutral", "positive"]
TWITTER_LABELS = {0: "negative", 1: "positive", 2: "neutral"}  # Bearish, Bullish, Neutral


def download_all(refresh: bool = False) -> None:
    for name, url in FILES.items():
        download(url, TEXT_DIR / name, refresh=refresh, manifest=MANIFEST)


def load_twitter(split: str) -> pd.DataFrame:
    df = pd.read_csv(TEXT_DIR / f"twitter_fin_{split}.csv")
    return pd.DataFrame({"text": df["text"].astype(str), "label": df["label"].map(TWITTER_LABELS)})


def load_phrasebank(agreement: str = "AllAgree") -> pd.DataFrame:
    with zipfile.ZipFile(TEXT_DIR / "FinancialPhraseBank-v1.0.zip") as zf:
        name = next(n for n in zf.namelist() if n.endswith(f"Sentences_{agreement}.txt"))
        lines = zf.read(name).decode("latin-1").splitlines()
    rows = [line.rsplit("@", 1) for line in lines if "@" in line]
    return pd.DataFrame(rows, columns=["text", "label"]).assign(label=lambda d: d["label"].str.strip())


if __name__ == "__main__":
    setup_logging()
    download_all()
    for split in ("train", "valid"):
        print(split, load_twitter(split)["label"].value_counts().to_dict())
    print("phrasebank", load_phrasebank()["label"].value_counts().to_dict())
