"""Build the M7 distress dataset: one row per 10-K, features as of its filed date (ML_PIPELINE §4, §5).

Label = the company files an 8-K Item 1.03 (bankruptcy or receivership) within 12 months after the
10-K was filed. Rows where the company already reported a bankruptcy in the previous 24 months are
dropped (the model is an early-warning model, not a "currently bankrupt" detector). Financial
companies (SIC 6000-6999) are excluded; banks use the separate bank variant of the Financial pillar.

    python -m pipelines.features.distress_dataset [--workers 16]
"""

from __future__ import annotations

import argparse
import logging
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from pipelines.common import PROCESSED_DIR, is_financial_sic, sector_for_sic, setup_logging
from pipelines.features import financial
from pipelines.features.events import EVENT_FEATURES, canonical_events, event_features

log = logging.getLogger("echo.features.distress")

SEC_DIR = PROCESSED_DIR / "sec"
OUT = PROCESSED_DIR / "features" / "distress.parquet"
FIRST_FILED, LAST_FILED = pd.Timestamp("2010-01-01"), pd.Timestamp("2024-12-31")
HORIZON_DAYS = 365
EXCLUDE_PRIOR_DAYS = 730
FEATURE_COLUMNS = financial.FEATURES + list(EVENT_FEATURES.values())
STORED_COLUMNS = FEATURE_COLUMNS + financial.FORENSIC_FEATURES


def _company_rows(cik: int, facts: pd.DataFrame, filings: pd.DataFrame, events: pd.DataFrame) -> list[dict]:
    tenks = filings[filings["form"].isin(["10-K", "10-KT"]) & filings["filed"].between(FIRST_FILED, LAST_FILED)]
    bankruptcies = events.loc[events["event"] == "BANKRUPTCY", "filed"].to_numpy()
    store = financial.FactStore(facts)
    rows = []
    for filed, report_date, accn in zip(tenks["filed"], tenks["report_date"], tenks["accn"], strict=True):
        prior = bankruptcies[(bankruptcies <= filed) & (bankruptcies > filed - pd.Timedelta(days=EXCLUDE_PRIOR_DAYS))]
        if len(prior):
            continue
        latest = (report_date, filed) if pd.notna(report_date) else None
        feats, snap = financial.build(store, filed, latest_filing=latest)
        if snap.period_end is None or (filed - snap.period_end).days > 400:
            continue  # no usable balance sheet at this date
        feats.update(event_features(events, filed))
        future = bankruptcies[(bankruptcies > filed) & (bankruptcies <= filed + pd.Timedelta(days=HORIZON_DAYS))]
        rows.append({
            "cik": cik, "accn": accn, "as_of": filed, "period_end": snap.period_end,
            "label": int(len(future) > 0),
            "label_date": pd.Timestamp(future.min()) if len(future) else pd.NaT,
            **feats,
        })
    return rows


def _process_batch(args: tuple[list[int], pd.DataFrame, pd.DataFrame]) -> list[dict]:
    ciks, filings, events = args
    facts = pq.read_table(SEC_DIR / "facts.parquet", filters=[("cik", "in", ciks)]).to_pandas()
    rows = []
    for cik in ciks:
        rows.extend(_company_rows(cik, facts[facts["cik"] == cik], filings[filings["cik"] == cik],
                                  events[events["cik"] == cik]))
    return rows


def main(workers: int) -> pd.DataFrame:
    companies = pd.read_parquet(SEC_DIR / "companies.parquet")
    filings = pd.read_parquet(SEC_DIR / "filings.parquet")
    companies = companies[companies["sic"].notna() & ~companies["sic"].map(is_financial_sic)]
    ciks = sorted(set(companies["cik"]) & set(filings.loc[filings["form"].isin(["10-K", "10-KT"]), "cik"]))
    filings = filings[filings["cik"].isin(ciks)]
    events = canonical_events(filings)
    log.info("Building distress rows for %d non-financial companies", len(ciks))

    batches = [ciks[i:i + 250] for i in range(0, len(ciks), 250)]
    rows: list[dict] = []
    with ProcessPoolExecutor(workers) as pool:
        payloads = [(b, filings[filings["cik"].isin(b)], events[events["cik"].isin(b)]) for b in batches]
        for i, batch_rows in enumerate(pool.map(_process_batch, payloads)):
            rows.extend(batch_rows)
            log.info("  batch %d/%d -> %d rows", i + 1, len(batches), len(rows))

    df = pd.DataFrame(rows)
    meta = companies.set_index("cik")[["name", "sic"]]
    df = df.join(meta, on="cik")
    df["sector"] = df["sic"].map(sector_for_sic)
    df["year"] = df["as_of"].dt.year
    df[STORED_COLUMNS] = df[STORED_COLUMNS].astype(float).replace([np.inf, -np.inf], np.nan)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    log.info("Wrote %s: %d rows, %d positives (%.2f%%)", OUT, len(df), df["label"].sum(), 100 * df["label"].mean())
    return df


if __name__ == "__main__":
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=16)
    main(parser.parse_args().workers)
