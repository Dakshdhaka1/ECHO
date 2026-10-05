"""Record the demo snapshot (DATA_STRATEGY §6) with the live providers in record mode.

    python -m pipelines.ingestion.record_sample [--skip-news] [--only CIK ...]

Writes data/sample/sec/{cik}/*.json.gz (public-domain SEC data), data/sample/news/{cik}.json (GDELT
headline metadata) and data/sample/MANIFEST.json (sha256, URL, retrieval time per file). Prices are
recorded to git-ignored data/raw/prices/ only (licence L1).
"""

from __future__ import annotations

import argparse
import logging
from datetime import UTC, datetime

import yaml

from app.adapters.base import CompanyRef
from app.adapters.news import GDELT_URL, GdeltNewsSource
from app.adapters.prices import SECTOR_ETF, AlphaVantagePriceSource
from app.adapters.sec import FACTS_URL, SUBMISSIONS_URL, UsSecProvider
from app.core.cache import ResponseCache
from app.core.config import get_settings
from pipelines.common import RAW_DIR, SAMPLE_DIR, sec_user_agent, sector_for_sic, setup_logging, update_manifest

log = logging.getLogger("echo.ingestion.record_sample")


def _record_price(prices: AlphaVantagePriceSource, ticker: str, kind: str) -> bool:
    """Record one series unless it was already recorded today; False when the daily quota is exhausted."""
    suffix = "_weekly" if kind == "weekly" else ""
    path = RAW_DIR / "prices" / f"{ticker.upper()}{suffix}.csv"
    if path.exists() and datetime.fromtimestamp(path.stat().st_mtime).date() == datetime.now().date():
        log.info("  %s %s: already recorded today", ticker, kind)
        return True
    result = getattr(prices, kind)(ticker)
    if result.available:
        log.info("  %s %s: %d rows recorded", ticker, kind, len(result.data))
        return True
    log.warning("  %s %s unavailable: %s", ticker, kind, result.unavailable_reason)
    reason = (result.unavailable_reason or "").lower()
    return not any(word in reason for word in ("rate limit", "requests per day", "25 requests", "premium"))


def main(skip_news: bool, only: list[int] | None, news_only: bool = False, prices_only: bool = False) -> None:
    settings = get_settings()
    cache = ResponseCache(settings.redis_host, settings.redis_port, enabled=False)
    sec = UsSecProvider(SAMPLE_DIR, cache, mode="record", user_agent=sec_user_agent())
    replay_sec = UsSecProvider(SAMPLE_DIR, cache, mode="replay")  # reads the snapshot without re-recording it
    news = GdeltNewsSource(SAMPLE_DIR, cache, mode="record")
    prices = AlphaVantagePriceSource(settings.alpha_vantage_api_key, cache, record_dir=RAW_DIR / "prices")
    universe = yaml.safe_load((SAMPLE_DIR / "universe.yaml").read_text(encoding="utf-8"))["companies"]
    manifest = SAMPLE_DIR / "MANIFEST.json"
    sectors: set[str] = set()

    for c in universe:
        cik = int(c["cik"])
        if only and cik not in only:
            continue
        ref = CompanyRef("US_SEC", f"{cik:010d}", c.get("ticker"), c["name"])
        log.info("Recording %s (CIK %d)", c["name"], cik)
        if not news_only and not prices_only:
            sec.raw_submissions(cik)
            sec.raw_companyfacts(cik)
            company_dir = SAMPLE_DIR / "sec" / str(cik)
            update_manifest(manifest, company_dir / "submissions.json.gz",
                            SUBMISSIONS_URL.format(name=f"CIK{cik:010d}.json"))
            update_manifest(manifest, company_dir / "companyfacts.json.gz", FACTS_URL.format(cik=cik))
        if not skip_news and not prices_only and "latest" in c.get("as_of", []):
            result = news.articles(ref, datetime.now(UTC), days=settings.news_window_days,
                                   query_override=c.get("news_query"))
            if result.available:
                update_manifest(manifest, SAMPLE_DIR / "news" / f"{cik}.json", GDELT_URL)
                log.info("  news: %d headlines after de-duplication", len(result.data["articles"]))
            else:
                log.warning("  news unavailable: %s", result.unavailable_reason)
        if settings.alpha_vantage_api_key and c.get("ticker") and "latest" in c.get("as_of", []) and not news_only:
            sectors.add(sector_for_sic(replay_sec.raw_submissions(cik)[0].get("sic")))  # read-only
            for kind in ("daily", "weekly"):
                if not _record_price(prices, c["ticker"], kind):
                    log.warning("Alpha Vantage quota reached after %d requests; stopping price recording",
                                AlphaVantagePriceSource.calls)
                    return
    if settings.alpha_vantage_api_key and not news_only:
        for etf in sorted({SECTOR_ETF[s] for s in sectors if s in SECTOR_ETF} | {"SPY"}):
            if not _record_price(prices, etf, "weekly"):
                log.warning("Alpha Vantage quota reached; ETF %s not recorded", etf)
                return
        log.info("Alpha Vantage requests used: %d (free tier: 25/day)", AlphaVantagePriceSource.calls)
    log.info("Snapshot written to %s", SAMPLE_DIR)


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-news", action="store_true")
    parser.add_argument("--only", type=int, nargs="*", help="record only these CIKs")
    parser.add_argument("--news-only", action="store_true", help="re-record GDELT news only")
    parser.add_argument("--prices-only", action="store_true",
                        help="record Alpha Vantage prices only (daily last 100 days + weekly adjusted history)")
    args = parser.parse_args()
    main(args.skip_news, args.only, args.news_only, args.prices_only)
