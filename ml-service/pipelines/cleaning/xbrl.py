"""XBRL companyfacts JSON -> canonical facts (DATA_STRATEGY §2).

Used by the bulk cleaning pipeline (training universe) and by the live/replay providers (inference),
so both see exactly the same canonical items.
"""

from __future__ import annotations

import pandas as pd

from pipelines.common import load_mapping

FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A", "10-KT", "10-KT/A"})
COLUMNS = ["item", "rank", "start", "end", "val", "fy", "fp", "form", "filed", "accn"]


def extract_canonical_facts(companyfacts: dict, min_filed: str = "2009-01-01") -> pd.DataFrame:
    """Return one row per distinct reported value of every mapped tag.

    A value that is repeated unchanged in later filings (e.g. prior-year comparatives) is kept only
    with its *first* filed date, so a point-in-time query sees it from the moment it became public.
    Restated values (different `val` for the same period) are kept as separate rows.
    """
    mapping = load_mapping("us_gaap.yaml")["items"]
    facts = companyfacts.get("facts", {})
    rows: list[tuple] = []
    for item, spec in mapping.items():
        unit = spec.get("unit", "USD")
        for rank, tag in enumerate(spec["tags"]):
            taxonomy, name = tag.split(":")
            entry = facts.get(taxonomy, {}).get(name)
            if not entry:
                continue
            for f in entry.get("units", {}).get(unit, []):
                if f.get("form") not in FORMS or f.get("filed", "") < min_filed:
                    continue
                rows.append((item, rank, f.get("start"), f["end"], float(f["val"]), f.get("fy"),
                             f.get("fp"), f["form"], f["filed"], f["accn"]))
    df = pd.DataFrame(rows, columns=COLUMNS)
    if df.empty:
        return df
    for col in ("start", "end", "filed"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df = df.dropna(subset=["end", "filed"])
    lo, hi = pd.Timestamp("1990-01-01"), pd.Timestamp("2100-01-01")
    df = df[df["end"].between(lo, hi) & df["filed"].between(lo, hi) & (df["start"].isna() | df["start"].between(lo, hi))]
    df["rank"] = df["rank"].astype("int8")
    df = df.sort_values("filed", kind="stable")
    df = df.drop_duplicates(subset=["item", "rank", "start", "end", "val"], keep="first")
    return df.reset_index(drop=True)
