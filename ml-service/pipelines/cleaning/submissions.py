"""EDGAR submissions JSON -> company metadata + filings table (shared by bulk cleaning and providers)."""

from __future__ import annotations

import json
import re

import pandas as pd

KEEP_FORMS = re.compile(r"^(10-K|10-KT|10-Q|8-K|NT 10-K|NT 10-Q|15-12B|15-12G|15-15D|25|25-NSE)(/A)?$")
FILING_FIELDS = ["accessionNumber", "filingDate", "reportDate", "form", "items", "primaryDocument"]
FILING_COLUMNS = ["cik", "accn", "filed", "report_date", "form", "items", "primary_document"]


def filings_frame(cik: int, block: dict) -> pd.DataFrame:
    """One block of parallel arrays ('recent' or an overflow page) -> filings rows we care about."""
    if not block or not block.get("accessionNumber"):
        return pd.DataFrame(columns=FILING_COLUMNS)
    n = len(block["accessionNumber"])
    df = pd.DataFrame({f: block.get(f) or [None] * n for f in FILING_FIELDS})
    df = df[df["form"].fillna("").str.match(KEEP_FORMS)]
    df.insert(0, "cik", cik)
    return df.rename(columns={"accessionNumber": "accn", "filingDate": "filed", "reportDate": "report_date",
                              "primaryDocument": "primary_document"})


def finalize_filings(df: pd.DataFrame) -> pd.DataFrame:
    df = df.drop_duplicates("accn").copy()
    df["filed"] = pd.to_datetime(df["filed"], errors="coerce")
    df["report_date"] = pd.to_datetime(df["report_date"].replace("", None), errors="coerce")
    df["items"] = df["items"].fillna("")
    return df.sort_values("filed").reset_index(drop=True)


def parse_submissions(data: dict, overflow_pages: list[dict] | None = None) -> tuple[dict, pd.DataFrame]:
    """Full submissions document (+ optional overflow pages) -> (company meta, filings)."""
    cik = int(data["cik"])
    meta = {
        "cik": cik,
        "name": data.get("name"),
        "tickers": [t for t in data.get("tickers", []) if t],
        "exchanges": [e for e in data.get("exchanges", []) if e],
        "sic": data.get("sic") or None,
        "sic_description": data.get("sicDescription"),
        "entity_type": data.get("entityType"),
        "state_of_incorporation": data.get("stateOfIncorporation"),
        "fiscal_year_end": data.get("fiscalYearEnd"),
        "former_names": data.get("formerNames", []),
    }
    frames = [filings_frame(cik, data.get("filings", {}).get("recent", {}))]
    frames += [filings_frame(cik, page) for page in overflow_pages or []]
    frames = [f for f in frames if not f.empty]
    filings = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=FILING_COLUMNS)
    return meta, finalize_filings(filings)


def meta_row(meta: dict) -> dict:
    """Flatten list fields for parquet storage."""
    row = dict(meta)
    row["tickers"] = "|".join(meta["tickers"])
    row["exchanges"] = "|".join(meta["exchanges"])
    row["former_names"] = json.dumps(meta["former_names"])
    return row
