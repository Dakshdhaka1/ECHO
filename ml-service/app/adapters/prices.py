"""Daily price sources (pluggable `PriceSource`, DATA_STRATEGY §1).

* CsvPriceSource - CSV files placed in data/sample/prices/ (committed, once licence L1 is cleared) or
  data/raw/prices/ (local, git-ignored). Columns: date, open, high, low, close, volume.
* AlphaVantagePriceSource - free API key (ALPHA_VANTAGE_API_KEY); responses are cached for 24h and,
  in record mode, written to data/raw/prices/ (never to the committed sample, see licence L1).

Free daily series are not split-adjusted, so `adjust_splits` removes split discontinuities
(otherwise every split would look like a -50%/-90% crash to the market pillar and anomaly model).
"""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from app.adapters.base import SourceResult
from app.core.cache import ResponseCache

log = logging.getLogger(__name__)

AV_URL = "https://www.alphavantage.co/query"
SPLIT_RATIOS = (2, 3, 4, 5, 8, 10, 15, 20, 25, 30, 40, 50)
SECTOR_ETF = {
    "Information Technology": "XLK", "Financials": "XLF", "Health Care": "XLV", "Energy": "XLE",
    "Industrials": "XLI", "Consumer Discretionary": "XLY", "Consumer Staples": "XLP", "Utilities": "XLU",
    "Materials": "XLB", "Real Estate": "XLRE", "Communication Services": "XLC",
}
BENCHMARK = "SPY"


def adjust_splits(df: pd.DataFrame, tolerance: float = 0.03) -> tuple[pd.DataFrame, list[dict]]:
    """Detect forward/reverse splits from overnight price ratios close to k:1 and back-adjust history."""
    df = df.sort_index().copy()
    ratio = (df["open"] / df["close"].shift(1)).to_numpy()
    splits = []
    factor = np.ones(len(df))
    for i in range(1, len(df)):
        r = ratio[i]
        if not np.isfinite(r) or r <= 0:
            continue
        for k in SPLIT_RATIOS:
            if abs(r * k - 1) <= tolerance:        # forward split k:1 (price drops to 1/k)
                factor[:i] /= k
                splits.append({"date": df.index[i].date().isoformat(), "ratio": f"{k}:1"})
                break
            if abs(r / k - 1) <= tolerance:        # reverse split 1:k
                factor[:i] *= k
                splits.append({"date": df.index[i].date().isoformat(), "ratio": f"1:{k}"})
                break
    for col in ("open", "high", "low", "close"):
        df[col] = df[col] * factor
    df["volume"] = df["volume"] / factor
    return df, splits


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def _normalise_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Weekly series; `close` is the split- and dividend-adjusted close (raw close kept as `raw_close`)."""
    df.columns = [c.strip().lower() for c in df.columns]
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    out = df[["open", "high", "low", "close", "volume"]].astype(float).rename(columns={"close": "raw_close"})
    out["close"] = df["adjusted_close"].astype(float)
    return out


class CsvPriceSource:
    """Recorded or user-supplied CSVs: TICKER.csv (daily OHLCV) and TICKER_weekly.csv (weekly adjusted)."""

    name = "csv_prices"

    def __init__(self, directories: list[Path]):
        self.directories = directories

    def _find(self, filename: str) -> Path | None:
        return next((d / filename for d in self.directories if (d / filename).exists()), None)

    def daily(self, ticker: str) -> SourceResult[pd.DataFrame]:
        path = self._find(f"{ticker.upper()}.csv")
        if path is None:
            return SourceResult.unavailable(self.name, f"no daily price file for {ticker}")
        df, splits = adjust_splits(_normalise(pd.read_csv(path)))
        df.attrs["splits"] = splits
        return SourceResult.ok(df, f"{self.name}:{path.parent.name}", [path.as_posix()],
                               datetime.fromtimestamp(path.stat().st_mtime, UTC))

    def weekly(self, ticker: str) -> SourceResult[pd.DataFrame]:
        path = self._find(f"{ticker.upper()}_weekly.csv")
        if path is None:
            return SourceResult.unavailable(self.name, f"no weekly price file for {ticker}")
        return SourceResult.ok(_normalise_weekly(pd.read_csv(path)), f"{self.name}:{path.parent.name}",
                               [path.as_posix()], datetime.fromtimestamp(path.stat().st_mtime, UTC))


class AlphaVantagePriceSource:
    """Alpha Vantage free tier: the daily series is limited to the latest 100 trading days (full daily history is
    premium), while the weekly adjusted series has full history. Recorded daily files are merged, so the local
    daily history grows with every recording."""

    name = "alpha_vantage"
    calls = 0  # requests made by this process (the free tier allows 25 per day)

    def __init__(self, api_key: str, cache: ResponseCache, record_dir: Path | None = None, timeout: float = 30.0,
                 min_interval: float = 2.0):
        self.api_key = api_key
        self.cache = cache
        self.record_dir = record_dir
        self._timeout = timeout
        self._min_interval = min_interval
        self._last = 0.0

    def _query(self, function: str, ticker: str, series_key: str, extra: dict | None = None):
        """Response JSON, or an error message string."""
        if not self.api_key:
            return "ALPHA_VANTAGE_API_KEY not set"
        cache_key = f"av:{function}:{ticker.upper()}"
        data = self.cache.get_json(cache_key)
        if data is not None:
            return data
        wait = self._min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = httpx.get(AV_URL, timeout=self._timeout,
                             params={"function": function, "symbol": ticker, "apikey": self.api_key, **(extra or {})})
            AlphaVantagePriceSource.calls += 1
            self._last = time.monotonic()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            return f"Alpha Vantage request failed: {exc}"
        if series_key not in data:
            msg = data.get("Note") or data.get("Information") or data.get("Error Message") or "no data"
            return f"Alpha Vantage: {msg[:160]}"
        self.cache.set_json(cache_key, data, ttl_seconds=86400)
        return data

    def daily(self, ticker: str) -> SourceResult[pd.DataFrame]:
        data = self._query("TIME_SERIES_DAILY", ticker, "Time Series (Daily)", {"outputsize": "compact"})
        if isinstance(data, str):
            return SourceResult.unavailable(self.name, data)
        df = pd.DataFrame.from_dict(data["Time Series (Daily)"], orient="index")
        df.columns = ["open", "high", "low", "close", "volume"]
        df.index.name = "date"
        df = df.reset_index()
        if self.record_dir is not None:
            self.record_dir.mkdir(parents=True, exist_ok=True)
            path = self.record_dir / f"{ticker.upper()}.csv"
            if path.exists():  # merge: keep older recorded days, newer values win on overlap
                old = pd.read_csv(path, dtype=str)
                df = pd.concat([old[~old["date"].isin(df["date"])], df.astype(str)], ignore_index=True)
            df.sort_values("date").to_csv(path, index=False)
        adjusted, splits = adjust_splits(_normalise(df))
        adjusted.attrs["splits"] = splits
        return SourceResult.ok(adjusted, self.name, [f"{AV_URL}?function=TIME_SERIES_DAILY&symbol={ticker}"])

    def weekly(self, ticker: str) -> SourceResult[pd.DataFrame]:
        data = self._query("TIME_SERIES_WEEKLY_ADJUSTED", ticker, "Weekly Adjusted Time Series")
        if isinstance(data, str):
            return SourceResult.unavailable(self.name, data)
        df = pd.DataFrame.from_dict(data["Weekly Adjusted Time Series"], orient="index")
        df.columns = ["open", "high", "low", "close", "adjusted_close", "volume", "dividend"]
        df.index.name = "date"
        df = df.reset_index()
        if self.record_dir is not None:
            self.record_dir.mkdir(parents=True, exist_ok=True)
            df.sort_values("date").to_csv(self.record_dir / f"{ticker.upper()}_weekly.csv", index=False)
        return SourceResult.ok(_normalise_weekly(df), self.name,
                               [f"{AV_URL}?function=TIME_SERIES_WEEKLY_ADJUSTED&symbol={ticker}"])


class PriceRouter:
    """Local CSVs first (recorded or user-supplied), then Alpha Vantage if a key is configured."""

    def __init__(self, sources: list):
        self.sources = sources

    def _first(self, method: str, ticker: str | None) -> SourceResult[pd.DataFrame]:
        if not ticker:
            return SourceResult.unavailable("prices", "company has no ticker")
        reasons = []
        for src in self.sources:
            result = getattr(src, method)(ticker)
            if result.available:
                return result
            reasons.append(result.unavailable_reason)
        return SourceResult.unavailable("prices", "; ".join(r for r in reasons if r))

    def daily(self, ticker: str | None) -> SourceResult[pd.DataFrame]:
        return self._first("daily", ticker)

    def weekly(self, ticker: str | None) -> SourceResult[pd.DataFrame]:
        return self._first("weekly", ticker)
