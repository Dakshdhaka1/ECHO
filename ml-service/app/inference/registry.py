"""Loads exported champion models from artifacts/<model>/<version>/ (no MLflow needed at runtime)."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

import joblib

from app.inference.sentiment import SentimentModel

log = logging.getLogger(__name__)


class ModelRegistry:
    def __init__(self, model_dir: Path):
        self.model_dir = model_dir
        self._cache: dict[str, tuple[str, Any, dict]] = {}
        self._lock = threading.Lock()

    def champion_version(self, name: str) -> str | None:
        pointer = self.model_dir / name / "CHAMPION"
        if pointer.exists():
            return pointer.read_text().strip()
        return None

    def card(self, name: str) -> dict | None:
        version = self.champion_version(name)
        if version is None:
            return None
        path = self.model_dir / name / version / "model_card.json"
        return json.loads(path.read_text()) if path.exists() else None

    def get(self, name: str) -> tuple[Any, dict] | tuple[None, None]:
        """(model, card) for the current champion, cached; reloads automatically after a promotion."""
        version = self.champion_version(name)
        if version is None:
            return None, None
        with self._lock:
            cached = self._cache.get(name)
            if cached and cached[0] == version:
                return cached[1], cached[2]
            directory = self.model_dir / name / version
            try:
                model = (SentimentModel.load(directory, version) if name == "news_sentiment"
                         else joblib.load(directory / "model.joblib"))
            except Exception as exc:
                log.error("Failed to load %s v%s: %s", name, version, exc)
                return None, None
            card = json.loads((directory / "model_card.json").read_text())
            self._cache[name] = (version, model, card)
            log.info("Loaded %s v%s", name, version)
            return model, card

    def versions(self) -> dict[str, str]:
        if not self.model_dir.is_dir():
            return {}
        return {p.name: v for p in sorted(self.model_dir.iterdir()) if p.is_dir() and (v := self.champion_version(p.name))}

    def all_cards(self) -> list[dict]:
        cards = []
        if not self.model_dir.is_dir():
            return cards
        for model_dir in sorted(p for p in self.model_dir.iterdir() if p.is_dir()):
            champion = self.champion_version(model_dir.name)
            for card_path in sorted(model_dir.glob("*/model_card.json"), key=lambda p: int(p.parent.name)
                                    if p.parent.name.isdigit() else 0):
                card = json.loads(card_path.read_text())
                card["is_champion"] = card.get("version") == champion
                card.pop("config", None)
                cards.append(card)
        return cards
