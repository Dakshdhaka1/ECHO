"""Serving wrapper for the M1 news-sentiment champion (ONNX transformer or scikit-learn pipeline)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

LABELS = ["negative", "neutral", "positive"]


class SentimentModel:
    def __init__(self, predict_fn, labels: list[str], version: str = ""):
        self._predict = predict_fn
        self._order = [labels.index(label) for label in LABELS]  # reorder columns to LABELS
        self.version = version

    @classmethod
    def load(cls, directory: Path, version: str = "") -> SentimentModel:
        meta = json.loads((directory / "labels.json").read_text())
        if meta["format"] == "onnx":
            import onnxruntime as ort
            from tokenizers import Tokenizer

            session = ort.InferenceSession(str(directory / "model.onnx"), providers=["CPUExecutionProvider"])
            tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
            tokenizer.enable_truncation(meta["max_length"])
            tokenizer.enable_padding(pad_id=tokenizer.token_to_id("<pad>") or 1, pad_token="<pad>")

            def predict(texts: list[str]) -> np.ndarray:
                out = []
                for i in range(0, len(texts), 64):
                    enc = tokenizer.encode_batch(texts[i:i + 64])
                    ids = np.array([e.ids for e in enc], dtype=np.int64)
                    mask = np.array([e.attention_mask for e in enc], dtype=np.int64)
                    logits = session.run(["logits"], {"input_ids": ids, "attention_mask": mask})[0]
                    exp = np.exp(logits - logits.max(axis=1, keepdims=True))
                    out.append(exp / exp.sum(axis=1, keepdims=True))
                return np.vstack(out)

            return cls(predict, meta["labels"], version)
        import joblib

        pipe = joblib.load(directory / "model.joblib")
        return cls(lambda texts: pipe.predict_proba(texts), list(pipe.classes_), version)

    def predict_proba(self, texts: list[str]) -> np.ndarray:
        """Probabilities in LABELS order (negative, neutral, positive)."""
        if not texts:
            return np.zeros((0, 3))
        return self._predict(list(texts))[:, self._order]

    def score(self, texts: list[str]) -> tuple[np.ndarray, list[str]]:
        """Polarity in [-1, 1] = P(pos) - P(neg), plus the arg-max label."""
        p = self.predict_proba(texts)
        return p[:, 2] - p[:, 0], [LABELS[i] for i in p.argmax(axis=1)]
