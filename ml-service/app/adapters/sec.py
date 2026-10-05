"""US SEC market provider: identity, XBRL facts and filings (DATA_STRATEGY §1-2).

Modes:
  live   - data.sec.gov / www.sec.gov APIs (rate limited, contact User-Agent, cached)
  replay - recorded files under data/sample/sec/{cik}/ (demo mode, no network)
  record - live, and every response is also written to data/sample for later replay
"""

from __future__ import annotations

import gzip
import json
import logging
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pandas as pd
import yaml
from rapidfuzz import fuzz, process
from rapidfuzz.utils import default_process

from app.adapters.base import CompanyCandidate, CompanyRef, ProviderError, SourceResult
from app.core.cache import ResponseCache
from pipelines.cleaning.submissions import parse_submissions
from pipelines.cleaning.xbrl import extract_canonical_facts
from pipelines.common import DEFAULT_SEC_USER_AGENT

log = logging.getLogger(__name__)

MARKET = "US_SEC"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
FILING_INDEX_URL = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik:010d}&type={form}"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn_nodash}/{doc}"
SUFFIXES = (" inc", " inc.", " corp", " corp.", " corporation", " co", " co.", " company", " ltd", " plc",
            " holdings", " group", " platforms", " /de/", " /new/")


def short_name(name: str) -> str:
    """'Apple Inc.' -> 'Apple' (used for news queries and fuzzy matching)."""
    n = name.strip()
    lowered = n.lower()
    changed = True
    while changed:
        changed = False
        for suffix in SUFFIXES:
            if lowered.endswith(suffix):
                n, lowered = n[: -len(suffix)].rstrip(" ,"), lowered[: -len(suffix)].rstrip(" ,")
                changed = True
    return n


def filing_url(cik: int, accn: str, document: str | None) -> str:
    if document:
        return ARCHIVE_URL.format(cik=cik, accn_nodash=accn.replace("-", ""), doc=document)
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/"


class UsSecProvider:
    market = MARKET

    def __init__(self, sample_dir: Path, cache: ResponseCache, mode: str = "replay", user_agent: str = "",
                 timeout: float = 20.0):
        if mode not in {"live", "replay", "record"}:
            raise ValueError(f"unknown mode {mode}")
        self.mode = mode
        self.sample_dir = sample_dir
        self.cache = cache
        self._headers = {"User-Agent": user_agent or DEFAULT_SEC_USER_AGENT, "Accept-Encoding": "gzip, deflate"}
        self._timeout = timeout
        self._lock = threading.Lock()
        self._last_request = 0.0
        self._universe = self._load_universe()

    # ------------------------------------------------------------------ helpers
    def _load_universe(self) -> list[dict]:
        path = self.sample_dir / "universe.yaml"
        if not path.exists():
            return []
        return yaml.safe_load(path.read_text(encoding="utf-8")).get("companies", [])

    def universe_entry(self, cik: int) -> dict | None:
        return next((c for c in self._universe if int(c["cik"]) == int(cik)), None)

    def _company_dir(self, cik: int) -> Path:
        return self.sample_dir / "sec" / str(int(cik))

    def _http_json(self, url: str, cache_key: str, ttl: int) -> dict:
        cached = self.cache.get_json(cache_key)
        if cached is not None:
            return cached
        with self._lock:  # SEC fair-access policy: at most 10 requests per second
            wait = 0.12 - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
        try:
            resp = httpx.get(url, headers=self._headers, timeout=self._timeout, follow_redirects=True)
        except httpx.HTTPError as exc:
            raise ProviderError(f"SEC request failed: {exc}") from exc
        if resp.status_code == 404:
            raise FileNotFoundError(url)
        if resp.status_code != 200:
            raise ProviderError(f"SEC returned HTTP {resp.status_code} for {url}")
        data = resp.json()
        self.cache.set_json(cache_key, data, ttl)
        return data

    @staticmethod
    def _write_gz(path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump(data, fh)

    @staticmethod
    def _read_gz(path: Path) -> dict:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)

    def _recorded_at(self, path: Path) -> datetime:
        manifest = self.sample_dir / "MANIFEST.json"
        if manifest.exists():
            entry = json.loads(manifest.read_text()).get(path.relative_to(self.sample_dir).as_posix())
            if entry:
                return datetime.fromisoformat(entry["retrieved_at"])
        return datetime.fromtimestamp(path.stat().st_mtime, UTC)

    # ------------------------------------------------------------------ identity
    def _ticker_rows(self) -> list[dict]:
        rows = []
        if self.mode != "replay":
            try:
                data = self._http_json(TICKERS_URL, "sec:company_tickers", ttl=86400)
                rows = [{"cik": int(r["cik_str"]), "ticker": r["ticker"], "name": r["title"]} for r in data.values()]
            except (ProviderError, FileNotFoundError) as exc:
                log.warning("company_tickers.json unavailable: %s", exc)
        known = {r["cik"] for r in rows}
        for c in self._universe:  # demo universe incl. delisted case-study companies
            if int(c["cik"]) not in known:
                rows.append({"cik": int(c["cik"]), "ticker": c.get("ticker"), "name": c["name"]})
        return rows

    def _former_names(self, cik: int) -> list[str]:
        path = self._company_dir(cik) / "submissions.json.gz"
        if not path.exists():
            return []
        main = self._read_gz(path)["main"]
        return [f["name"] for f in main.get("formerNames", []) if f.get("name")]

    def resolve(self, query: str, limit: int = 8) -> list[CompanyCandidate]:
        query = query.strip()
        if not query:
            return []
        rows = self._ticker_rows()
        demo_ciks = {int(c["cik"]) for c in self._universe}
        aliases: list[str] = []
        owner: list[int] = []
        for i, r in enumerate(rows):
            names = [r["name"], short_name(r["name"])]
            if int(r["cik"]) in demo_ciks:
                names += self._former_names(r["cik"])
            for name in dict.fromkeys(names):
                aliases.append(name)
                owner.append(i)
        q_upper = query.upper()
        ranked: dict[int, float] = {i: 100.0 for i, r in enumerate(rows) if (r.get("ticker") or "").upper() == q_upper}
        scored = process.extract(query, aliases, scorer=fuzz.WRatio, processor=default_process, limit=limit * 6)
        for _, score, alias_idx in scored:
            idx = owner[alias_idx]
            ranked[idx] = max(ranked.get(idx, 0.0), float(score))
        out = []
        for idx, score in sorted(ranked.items(), key=lambda kv: -kv[1])[:limit]:
            r = rows[idx]
            if score < 60:
                continue
            out.append(CompanyCandidate(
                market=MARKET, market_id=f"{int(r['cik']):010d}", name=r["name"], ticker=r.get("ticker"),
                former_names=self._former_names(r["cik"]) if int(r["cik"]) in demo_ciks else [],
                match_score=round(score / 100.0, 3), is_demo=int(r["cik"]) in demo_ciks,
            ))
        return out

    # ------------------------------------------------------------------ documents
    def raw_submissions(self, cik: int) -> tuple[dict, list[dict], datetime, str]:
        path = self._company_dir(cik) / "submissions.json.gz"
        url = SUBMISSIONS_URL.format(name=f"CIK{cik:010d}.json")
        if self.mode == "replay":
            if not path.exists():
                raise FileNotFoundError(f"no recorded submissions for CIK {cik}")
            doc = self._read_gz(path)
            return doc["main"], doc["overflow"], self._recorded_at(path), url
        main = self._http_json(url, f"sec:submissions:{cik}", ttl=6 * 3600)
        overflow = [self._http_json(SUBMISSIONS_URL.format(name=f["name"]), f"sec:submissions:{f['name']}", 86400)
                    for f in main.get("filings", {}).get("files", [])]
        if self.mode == "record":
            self._write_gz(path, {"main": main, "overflow": overflow})
        return main, overflow, datetime.now(UTC), url

    def raw_companyfacts(self, cik: int) -> tuple[dict, datetime, str]:
        path = self._company_dir(cik) / "companyfacts.json.gz"
        url = FACTS_URL.format(cik=cik)
        if self.mode == "replay":
            if not path.exists():
                raise FileNotFoundError(f"no recorded companyfacts for CIK {cik}")
            return self._read_gz(path), self._recorded_at(path), url
        data = self._http_json(url, f"sec:companyfacts:{cik}", ttl=6 * 3600)
        if self.mode == "record":
            self._write_gz(path, data)
        return data, datetime.now(UTC), url

    # ------------------------------------------------------------------ canonical outputs
    def company_profile(self, company: CompanyRef) -> SourceResult[tuple[dict, pd.DataFrame]]:
        cik = int(company.market_id)
        try:
            main, overflow, retrieved, url = self.raw_submissions(cik)
        except FileNotFoundError:
            return SourceResult.unavailable("sec_submissions", "no SEC filing history for this company")
        except ProviderError as exc:
            return SourceResult.unavailable("sec_submissions", str(exc))
        meta, filings = parse_submissions(main, overflow)
        return SourceResult.ok((meta, filings), "sec_submissions", [url], retrieved)

    def financial_facts(self, company: CompanyRef) -> SourceResult[pd.DataFrame]:
        cik = int(company.market_id)
        try:
            data, retrieved, url = self.raw_companyfacts(cik)
        except FileNotFoundError:
            return SourceResult.unavailable("sec_xbrl", "no XBRL financial statements filed")
        except ProviderError as exc:
            return SourceResult.unavailable("sec_xbrl", str(exc))
        facts = extract_canonical_facts(data)
        if facts.empty:
            return SourceResult.unavailable("sec_xbrl", "no US-GAAP facts mapped to ECHO line items")
        return SourceResult.ok(facts, "sec_xbrl", [url], retrieved)
