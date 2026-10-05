"""GDELT DOC 2.0 news source (headline metadata only; DATA_STRATEGY §1).

GDELT asks clients to send at most one request every 5 seconds, so live mode fetches a few
multi-week windows, while record mode (demo snapshot) fetches weekly windows for denser coverage.
Only title, URL, outlet domain and timestamp are kept; article bodies are never fetched or stored.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd

from app.adapters.base import CompanyRef, SourceResult
from app.adapters.sec import short_name
from app.core.cache import ResponseCache

log = logging.getLogger(__name__)

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
MIN_GAP_SECONDS = 30.0      # measured from the previous response; GDELT 429s at the documented 5 s
BACKOFF_SECONDS = 45.0
_TOKEN = re.compile(r"[a-z0-9]+")


def news_query(company: CompanyRef, override: str | None = None) -> str:
    if override:
        return override
    return f'"{short_name(company.name or "")}" sourcelang:english'


def match_terms(company: CompanyRef, query: str) -> list[re.Pattern]:
    """Headline must name the company: any quoted phrase of the query (or the short name), as whole words."""
    phrases = re.findall(r'"([^"]+)"', query) or [short_name(company.name or "")]
    return [re.compile(r"\b" + re.escape(p.lower()) + r"\b") for p in phrases if p]


def normalise_title(title: str) -> str:
    return " ".join(_TOKEN.findall(title.lower()))


STOPWORDS = frozenset("a an the and or of to in on for by with at from as is are was were be its it this that over "
                      "after into new says say said will has have had than more about up out amid vs".split())


def content_tokens(title: str) -> frozenset[str]:
    """Normalised content words with light stemming (sued/sues/suing -> sue), used for story matching."""
    out = set()
    for tok in normalise_title(title).split():
        if tok in STOPWORDS:
            continue
        for suffix in ("ing", "ed", "es", "s"):
            if len(tok) > 4 and tok.endswith(suffix):
                tok = tok[: -len(suffix)]
                break
        out.add(tok)
    return frozenset(out)


def deduplicate(articles: pd.DataFrame, overlap: float = 0.6, min_shared: int = 3, days: int = 3) -> pd.DataFrame:
    """One story = one headline. Syndicated or re-worded copies of a story are dropped when they share at least
    `min_shared` content words and `overlap` of the shorter headline's words, within `days` of the first copy
    (overlap coefficient; exact normalised duplicates always match). The earliest copy is kept."""
    if articles.empty:
        return articles
    df = articles.copy()
    df["norm"] = df["title"].map(normalise_title)
    df = df.sort_values("published_at").drop_duplicates("norm")
    kept: list[tuple[object, frozenset[str], pd.Timestamp]] = []
    for idx, title, ts in zip(df.index, df["title"], df["published_at"], strict=True):
        tokens = content_tokens(title)
        dup = False
        for _, other, other_ts in kept:
            shared = len(tokens & other)
            if abs((ts - other_ts).days) <= days and shared >= min_shared and                     shared / max(1, min(len(tokens), len(other))) >= overlap:
                dup = True
                break
        if not dup:
            kept.append((idx, tokens, ts))
    return df.loc[[k[0] for k in kept]].drop(columns="norm").reset_index(drop=True)


class GdeltNewsSource:
    name = "gdelt"

    def __init__(self, sample_dir: Path, cache: ResponseCache, mode: str = "replay", timeout: float = 45.0):
        self.mode = mode
        self.sample_dir = sample_dir
        self.cache = cache
        self._timeout = timeout
        self._lock = threading.Lock()
        self._last = 0.0

    def _get(self, params: dict) -> dict:
        key = "gdelt:" + json.dumps(params, sort_keys=True)
        cached = self.cache.get_json(key)
        if cached is not None:
            return cached
        for attempt in range(4):
            with self._lock:
                wait = MIN_GAP_SECONDS - (time.monotonic() - self._last)
                if wait > 0:
                    time.sleep(wait)
                try:
                    resp = httpx.get(GDELT_URL, params=params, timeout=self._timeout,
                                     headers={"User-Agent": "ECHO-academic-project"})
                finally:
                    self._last = time.monotonic()
            text = resp.text.strip()
            if resp.status_code == 200 and text.startswith("{"):
                data = json.loads(text)
                self.cache.set_json(key, data, ttl_seconds=3600)
                return data
            if resp.status_code == 200 and not text:  # GDELT returns an empty body for "no results"
                return {}
            log.info("GDELT throttled or failed (HTTP %s): %s", resp.status_code, text[:120])
            time.sleep(BACKOFF_SECONDS)
        raise RuntimeError("GDELT request failed after retries")

    def _fetch_live(self, query: str, end: datetime, days: int, windows: int, per_window: int) -> tuple[list, list]:
        articles, step = [], timedelta(days=days / windows)
        for w in range(windows):
            w_end = end - step * w
            w_start = w_end - step
            try:
                data = self._get({"query": query, "mode": "artlist", "format": "json", "sort": "datedesc",
                                  "maxrecords": per_window,
                                  "startdatetime": w_start.strftime("%Y%m%d%H%M%S"),
                                  "enddatetime": w_end.strftime("%Y%m%d%H%M%S")})
            except RuntimeError as exc:  # keep what the other windows returned
                log.warning("GDELT window %s..%s skipped: %s", w_start.date(), w_end.date(), exc)
                continue
            articles.extend(data.get("articles", []))
        if not articles:
            raise RuntimeError("no GDELT window returned data")
        try:
            vol = self._get({"query": query, "mode": "timelinevolraw", "format": "json",
                             "startdatetime": (end - timedelta(days=days)).strftime("%Y%m%d%H%M%S"),
                             "enddatetime": end.strftime("%Y%m%d%H%M%S")})
        except RuntimeError:
            vol = {}
        volume = vol.get("timeline", [{}])[0].get("data", []) if vol.get("timeline") else []
        return articles, volume

    @staticmethod
    def _to_frame(raw: list[dict], terms: list[re.Pattern]) -> pd.DataFrame:
        rows = []
        for a in raw:
            title = (a.get("title") or "").strip()
            if not title or not any(t.search(title.lower()) for t in terms):
                continue  # keep headlines that actually name the company
            try:
                ts = datetime.strptime(a["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            except (KeyError, ValueError):
                continue
            rows.append({"title": title, "url": a.get("url"), "domain": a.get("domain"),
                         "published_at": pd.Timestamp(ts), "source_country": a.get("sourcecountry")})
        df = pd.DataFrame(rows, columns=["title", "url", "domain", "published_at", "source_country"])
        return deduplicate(df)

    @staticmethod
    def _volume_frame(volume: list[dict]) -> pd.DataFrame:
        rows = [{"date": pd.Timestamp(datetime.strptime(v["date"][:8], "%Y%m%d")), "articles": v.get("value", 0)}
                for v in volume if v.get("date")]
        return pd.DataFrame(rows, columns=["date", "articles"])

    def articles(self, company: CompanyRef, as_of: datetime, days: int = 90,
                 query_override: str | None = None) -> SourceResult[dict]:
        """Returns {'articles': DataFrame, 'volume': DataFrame} for the `days` before `as_of`."""
        cik = int(company.market_id)
        path = self.sample_dir / "news" / f"{cik}.json"
        query = news_query(company, query_override)
        if self.mode == "replay":
            if not path.exists():
                return SourceResult.unavailable(self.name, "no recorded news for this company")
            doc = json.loads(path.read_text(encoding="utf-8"))
            recorded_end = datetime.fromisoformat(doc["window_end"])
            if as_of.date() < (recorded_end - timedelta(days=days)).date():
                return SourceResult.unavailable(
                    self.name, "news history before the GDELT 3-month window is not available")
            arts = self._to_frame(doc["articles"], match_terms(company, doc.get("query", query)))
            cutoff = pd.Timestamp(as_of) if as_of.tzinfo else pd.Timestamp(as_of, tz=UTC)
            arts = arts[arts["published_at"] <= cutoff]
            return SourceResult.ok({"articles": arts, "volume": self._volume_frame(doc["volume"]), "query": query},
                                   self.name, [GDELT_URL], datetime.fromisoformat(doc["retrieved_at"]))
        end = datetime.now(UTC)
        if (end.date() - as_of.date()).days > 7:
            return SourceResult.unavailable(self.name, "historical news is outside the GDELT DOC API 3-month window")
        windows, per_window = (3, 250) if self.mode == "record" else (2, 150)
        try:
            raw, volume = self._fetch_live(query, end, days, windows, per_window)
        except (httpx.HTTPError, RuntimeError) as exc:
            return SourceResult.unavailable(self.name, f"GDELT unavailable: {exc}")
        if self.mode == "record":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"query": query, "window_end": end.isoformat(), "retrieved_at": end.isoformat(),
                                        "articles": raw, "volume": volume}), encoding="utf-8")
        return SourceResult.ok({"articles": self._to_frame(raw, match_terms(company, query)),
                                "volume": self._volume_frame(volume), "query": query}, self.name, [GDELT_URL], end)
