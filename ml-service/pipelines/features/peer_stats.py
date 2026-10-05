"""Sector peer percentile tables (SCORING §2), rebuilt for every as-of date that is used.

For each as-of date: features of every SEC filer as known on that date (point-in-time), grouped by
ECHO sector, summarised as 101 quantiles (0..100%) per feature. Banks (SIC 6000-6399) also get the
bank-variant features in their own peer group. Output (committed for demo mode):
data/sample/reference/peer_stats_<as_of>.parquet

    python -m pipelines.features.peer_stats --as-of 2026-10-05 2022-12-31 ...   (default: demo universe dates)
"""

from __future__ import annotations

import argparse
import json
import logging
from concurrent.futures import ProcessPoolExecutor
from datetime import date

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import yaml

from pipelines.common import (
    PROCESSED_DIR,
    SAMPLE_DIR,
    is_bank_sic,
    sector_for_sic,
    setup_logging,
    update_manifest,
)
from pipelines.features import financial
from pipelines.features.bank import BANK_FEATURES, bank_features

log = logging.getLogger("echo.features.peer_stats")
QUANTILES = np.linspace(0, 1, 101)
PEER_FEATURES = financial.FEATURES
OUT_DIR = SAMPLE_DIR / "reference"
MIN_PEERS = 15


def _batch(args: tuple[list[int], dict[int, str], list[str]]) -> list[dict]:
    ciks, sics, as_ofs = args
    facts = pq.read_table(PROCESSED_DIR / "sec" / "facts.parquet", filters=[("cik", "in", ciks)]).to_pandas()
    rows = []
    for cik, f in facts.groupby("cik"):
        sic = sics.get(int(cik))
        store = financial.FactStore(f)
        for as_of in as_ofs:
            ts = pd.Timestamp(as_of)
            snap = financial.snapshot(store, ts)
            if snap.period_end is None or (ts - snap.period_end).days > 500:
                continue  # stale filer: not a peer on this date
            feats = financial.compute_features(snap)
            row = {"cik": int(cik), "as_of": as_of, "sector": sector_for_sic(sic), "bank": is_bank_sic(sic),
                   **{k: feats[k] for k in PEER_FEATURES}}
            if row["bank"]:
                row.update(bank_features(snap))
            rows.append(row)
    return rows


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    """Long table: (group, feature) -> n + 101 quantiles. 'ALL' is the market-wide fallback group."""
    out = []
    groups = [("ALL", df)] + [(s, g) for s, g in df.groupby("sector")] + [("BANKS", df[df["bank"]])]
    for name, g in groups:
        feats = PEER_FEATURES + (BANK_FEATURES if name == "BANKS" else [])
        for feat in feats:
            if feat not in g:
                continue
            vals = g[feat].replace([np.inf, -np.inf], np.nan).dropna().to_numpy()
            if len(vals) < MIN_PEERS:
                continue
            out.append({"group": name, "feature": feat, "n": len(vals),
                        "quantiles": json.dumps(np.quantile(vals, QUANTILES).round(6).tolist())})
    return pd.DataFrame(out)


def demo_dates() -> list[str]:
    universe = yaml.safe_load((SAMPLE_DIR / "universe.yaml").read_text(encoding="utf-8"))["companies"]
    dates = {d for c in universe for d in c["as_of"] if d != "latest"}
    dates.add(date.today().isoformat())
    return sorted(dates)


def main(as_ofs: list[str], workers: int) -> None:
    companies = pd.read_parquet(PROCESSED_DIR / "sec" / "companies.parquet", columns=["cik", "sic"])
    sics = dict(zip(companies["cik"].astype(int), companies["sic"], strict=True))
    ciks = sorted(sics)
    batches = [(ciks[i:i + 300], sics, as_ofs) for i in range(0, len(ciks), 300)]
    rows: list[dict] = []
    with ProcessPoolExecutor(workers) as pool:
        for i, part in enumerate(pool.map(_batch, batches)):
            rows.extend(part)
            if i % 10 == 0:
                log.info("  batch %d/%d", i + 1, len(batches))
    df = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for as_of, g in df.groupby("as_of"):
        table = summarise(g)
        path = OUT_DIR / f"peer_stats_{as_of}.parquet"
        table.to_parquet(path, index=False)
        update_manifest(SAMPLE_DIR / "MANIFEST.json", path, "derived: SEC companyfacts.zip (public domain)")
        log.info("%s: %d companies, %d (group, feature) rows", as_of, len(g), len(table))


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", nargs="*")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()
    main(args.as_of or demo_dates(), args.workers)
