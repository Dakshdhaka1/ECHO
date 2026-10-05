"""Bulk SEC archives -> processed parquet tables (DATA_STRATEGY §4).

Outputs (data/processed/sec/):
  companies.parquet  one row per operating company (filed at least one 10-K/10-Q)
  filings.parquet    10-K/10-Q/8-K/NT/deregistration filings with 8-K item codes
  facts.parquet      canonical XBRL facts (pipelines.cleaning.xbrl), filed >= 2009

    python -m pipelines.cleaning.sec_bulk [--workers 16] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import zipfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from pipelines.cleaning.submissions import filings_frame, finalize_filings, meta_row, parse_submissions
from pipelines.cleaning.xbrl import extract_canonical_facts
from pipelines.common import PROCESSED_DIR, RAW_DIR, setup_logging

log = logging.getLogger("echo.cleaning.sec_bulk")

SEC_RAW = RAW_DIR / "sec"
OUT_DIR = PROCESSED_DIR / "sec"
PRIMARY = re.compile(r"^CIK(\d{10})\.json$")
OVERFLOW = re.compile(r"^CIK(\d{10})-submissions-\d+\.json$")


def _parse_submissions_chunk(args: tuple[str, list[str]]) -> tuple[list[dict], pd.DataFrame]:
    zip_path, names = args
    companies, frames = [], []
    with zipfile.ZipFile(zip_path) as zf:
        for name in names:
            data = json.loads(zf.read(name))
            if (m := PRIMARY.match(name)) is None:  # overflow page: filings only
                frames.append(filings_frame(int(OVERFLOW.match(name).group(1)), data))
                continue
            recent = data.get("filings", {}).get("recent", {})
            has_periodic = any(f.startswith(("10-K", "10-Q")) for f in recent.get("form", []))
            if not has_periodic and not data.get("filings", {}).get("files"):
                continue
            data.setdefault("cik", m.group(1))
            meta, _ = parse_submissions({"cik": m.group(1), **{k: v for k, v in data.items() if k != "filings"}})
            companies.append(meta_row(meta))
            frames.append(filings_frame(int(m.group(1)), recent))
    frames = [f for f in frames if not f.empty]
    return companies, (pd.concat(frames, ignore_index=True) if frames else pd.DataFrame())


def _parse_facts_chunk(args: tuple[str, list[str]]) -> pd.DataFrame:
    zip_path, names = args
    frames = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in names:
            cik = int(PRIMARY.match(name).group(1))
            facts = extract_canonical_facts(json.loads(zf.read(name)))
            if not facts.empty:
                facts.insert(0, "cik", cik)
                frames.append(facts)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def clean_submissions(workers: int, limit: int | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    zip_path = SEC_RAW / "submissions.zip"
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if PRIMARY.match(n) or OVERFLOW.match(n)]
    if limit:
        names = names[:limit]
    log.info("Parsing %d submission files with %d workers", len(names), workers)
    companies, frames = [], []
    with ProcessPoolExecutor(workers) as pool:
        for comp, filings in pool.map(_parse_submissions_chunk, [(str(zip_path), c) for c in _chunks(names, 2000)]):
            companies.extend(comp)
            if not filings.empty:
                frames.append(filings)
    comp_df = pd.DataFrame(companies)
    filings = pd.concat(frames, ignore_index=True)
    filings = finalize_filings(filings[filings["cik"].isin(comp_df["cik"])])
    # Keep only entities that actually filed periodic reports (operating companies, not individuals/funds).
    periodic = filings[filings["form"].str.match(r"^10-[KQ]")]["cik"].unique()
    comp_df = comp_df[comp_df["cik"].isin(periodic)].reset_index(drop=True)
    filings = filings[filings["cik"].isin(periodic)].reset_index(drop=True)
    return comp_df, filings


def clean_companyfacts(ciks: set[int], workers: int, out: Path) -> int:
    zip_path = SEC_RAW / "companyfacts.zip"
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if (m := PRIMARY.match(n)) and int(m.group(1)) in ciks]
    log.info("Extracting canonical facts from %d companyfacts files", len(names))
    writer, rows = None, 0
    with ProcessPoolExecutor(workers) as pool:
        for i, df in enumerate(pool.map(_parse_facts_chunk, [(str(zip_path), c) for c in _chunks(names, 100)])):
            if df.empty:
                continue
            df["cik"] = df["cik"].astype("int32")
            df["fy"] = pd.to_numeric(df["fy"], errors="coerce").astype("float32")
            df["fp"] = df["fp"].astype("string")
            table = pa.Table.from_pandas(df, preserve_index=False)
            if writer is None:
                writer = pq.ParquetWriter(out, table.schema, compression="zstd")
            writer.write_table(table.cast(writer.schema))
            rows += len(df)
            if i % 20 == 0:
                log.info("  ... %d chunks, %d fact rows", i + 1, rows)
    if writer is not None:
        writer.close()
    return rows


def main(workers: int, limit: int | None, facts_only: bool = False) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if facts_only:
        companies = pd.read_parquet(OUT_DIR / "companies.parquet", columns=["cik"])
    else:
        companies, filings = clean_submissions(workers, limit)
        companies.to_parquet(OUT_DIR / "companies.parquet", index=False)
        filings.to_parquet(OUT_DIR / "filings.parquet", index=False)
        log.info("companies=%d filings=%d", len(companies), len(filings))
    rows = clean_companyfacts(set(companies["cik"]), workers, OUT_DIR / "facts.parquet")
    log.info("facts rows=%d", rows)


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--limit", type=int, default=None, help="debug: only the first N submission files")
    parser.add_argument("--facts-only", action="store_true", help="reuse companies/filings parquet")
    args = parser.parse_args()
    main(args.workers, args.limit, args.facts_only)
