"""Single entry point for training (ML_PIPELINE §2).

    python -m pipelines.run <model> [--config configs/<model>.yaml] [--no-promote]
    python -m pipelines.run all
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging

import yaml

from pipelines.common import CONFIGS_DIR, setup_logging

# model name -> training module (each exposes train(config) -> model card)
MODELS = {
    "news_sentiment": "pipelines.training.sentiment",
    "distress": "pipelines.training.distress",
    "peer_clusters": "pipelines.training.clustering",
    "financial_anomaly": "pipelines.training.financial_anomaly",
    "market_anomaly": "pipelines.training.market_anomaly",
    "revenue_forecast": "pipelines.training.forecast",
    "ocf_forecast": "pipelines.training.forecast",
    "review_sentiment": "pipelines.training.reviews",
}
ORDER = ["news_sentiment", "distress", "peer_clusters", "financial_anomaly", "market_anomaly", "revenue_forecast",
         "ocf_forecast", "review_sentiment"]

log = logging.getLogger("echo.run")


def run_model(name: str, config_path: str | None, promote: bool) -> dict:
    path = config_path or CONFIGS_DIR / f"{name}.yaml"
    config = yaml.safe_load(open(path, encoding="utf-8"))
    config["promote"] = promote
    module = importlib.import_module(MODELS[name])
    card = module.train(config)
    log.info("%s -> v%s stage=%s metrics=%s", name, card.get("version"), card.get("stage"),
             json.dumps(card.get("metrics"), default=float))
    return card


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=[*MODELS, "all"])
    parser.add_argument("--config")
    parser.add_argument("--no-promote", action="store_true")
    args = parser.parse_args()
    names = ORDER if args.model == "all" else [args.model]
    for name in names:
        try:
            run_model(name, args.config if len(names) == 1 else None, not args.no_promote)
        except FileNotFoundError as exc:
            log.error("%s skipped: missing input %s", name, exc)


if __name__ == "__main__":
    main()
