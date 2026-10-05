import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_model_cards(model_dir: Path) -> list[dict]:
    """Return the model_card.json of every exported model under <model_dir>/<model>/<version>/."""
    if not model_dir.is_dir():
        return []
    cards = []
    for path in sorted(model_dir.glob("*/*/model_card.json")):
        try:
            cards.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            logger.warning("Skipping unreadable model card %s", path)
    return cards
