"""Builds the provider/model graph once per process, from Settings (demo = replay, otherwise live)."""

from __future__ import annotations

from functools import lru_cache

from app.adapters.news import GdeltNewsSource
from app.adapters.prices import AlphaVantagePriceSource, CsvPriceSource, PriceRouter
from app.adapters.reviews import CsvReviewSource
from app.adapters.sec import UsSecProvider
from app.core.cache import ResponseCache
from app.core.config import ML_ROOT, Settings, get_settings
from app.inference.analyze import Analyzer, Services
from app.inference.peers import PeerStats
from app.inference.registry import ModelRegistry
from pipelines.monitoring.drift import InferenceLog


def build_services(settings: Settings) -> Services:
    cache = ResponseCache(settings.redis_host, settings.redis_port, enabled=settings.redis_enabled)
    mode = "replay" if settings.demo_mode else "live"
    price_sources = [CsvPriceSource([settings.sample_dir / "prices", settings.data_dir / "raw" / "prices"])]
    if not settings.demo_mode:
        price_sources.append(AlphaVantagePriceSource(settings.alpha_vantage_api_key, cache))
    return Services(
        sec=UsSecProvider(settings.sample_dir, cache, mode=mode, user_agent=settings.sec_user_agent,
                          timeout=settings.http_timeout_seconds),
        news=GdeltNewsSource(settings.sample_dir, cache, mode=mode),
        prices=PriceRouter(price_sources),
        reviews=CsvReviewSource(settings.data_dir / "raw" / "reviews" / "glassdoor_reviews.csv",
                                ML_ROOT / "mappings" / "review_firms.yaml"),
        registry=ModelRegistry(settings.model_dir),
        peers=PeerStats(settings.sample_dir / "reference"),
        explanation_provider=settings.explanation_provider,
        anthropic_api_key=settings.anthropic_api_key,
        llm_model=settings.llm_model,
        demo_mode=settings.demo_mode,
    )


@lru_cache
def get_services() -> Services:
    return build_services(get_settings())


@lru_cache
def get_analyzer() -> Analyzer:
    return Analyzer(get_services())


@lru_cache
def get_inference_log() -> InferenceLog:
    return InferenceLog(get_settings().monitoring_db)
