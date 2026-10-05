"""Employee reviews through `ReviewSource` (DATA_STRATEGY §1, decision D2).

Phase-1 source: the public Kaggle "Glassdoor Job Reviews" dataset, which the user downloads with
their own Kaggle account to data/raw/reviews/glassdoor_reviews.csv (it is never committed and never
scraped). `mappings/review_firms.yaml` maps the dataset's firm names to SEC CIKs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

from app.adapters.base import CompanyRef, SourceResult

REVIEW_COLUMNS = ["firm", "date_review", "overall_rating", "headline", "pros", "cons"]


@lru_cache(maxsize=2)
def _load(path: str, mtime: float, firms: frozenset[str]) -> pd.DataFrame:
    """Reviews of mapped employers only (keeps each API worker's memory small; the CSV has ~840k rows)."""
    parts = []
    for chunk in pd.read_csv(path, usecols=lambda c: c in REVIEW_COLUMNS + ["current", "job_title"],
                             chunksize=200_000, low_memory=False):
        parts.append(chunk[chunk["firm"].isin(firms)])
    df = pd.concat(parts, ignore_index=True)
    df["date_review"] = pd.to_datetime(df["date_review"], errors="coerce")
    return df.dropna(subset=["date_review"])


class CsvReviewSource:
    name = "kaggle_glassdoor"

    def __init__(self, csv_path: Path, firm_map_path: Path):
        self.csv_path = csv_path
        self.firm_map = {}
        if firm_map_path.exists():
            raw = yaml.safe_load(firm_map_path.read_text(encoding="utf-8")) or {}
            self.firm_map = {int(cik): firms for cik, firms in (raw.get("firms") or {}).items()}

    def reviews(self, company: CompanyRef, as_of: datetime) -> SourceResult[pd.DataFrame]:
        if not self.csv_path.exists():
            return SourceResult.unavailable(self.name, "employee-review dataset not downloaded (see README)")
        firms = self.firm_map.get(int(company.market_id))
        if not firms:
            return SourceResult.unavailable(self.name, "company is not in the employee-review dataset")
        all_firms = frozenset(f for names in self.firm_map.values() for f in names)
        df = _load(str(self.csv_path), self.csv_path.stat().st_mtime, all_firms)
        sub = df[df["firm"].isin(firms) & (df["date_review"] <= pd.Timestamp(as_of).tz_localize(None))]
        if sub.empty:
            return SourceResult.unavailable(self.name, "no reviews for this company before the analysis date")
        return SourceResult.ok(sub.copy(), self.name, ["https://www.kaggle.com/datasets/davidgauthier/glassdoor-job-reviews"],
                               datetime.fromtimestamp(self.csv_path.stat().st_mtime, UTC))
