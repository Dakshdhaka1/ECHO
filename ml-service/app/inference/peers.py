"""Peer percentile lookup over the tables built by pipelines.features.peer_stats."""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd


@lru_cache(maxsize=16)
def _load(path: str) -> dict[tuple[str, str], tuple[int, np.ndarray]]:
    df = pd.read_parquet(path)
    return {(g, f): (int(n), np.asarray(json.loads(q))) for g, f, n, q in
            zip(df["group"], df["feature"], df["n"], df["quantiles"], strict=True)}


class PeerStats:
    def __init__(self, reference_dir: Path):
        self.reference_dir = reference_dir

    def table_for(self, as_of: date) -> tuple[dict, str | None]:
        files = sorted(self.reference_dir.glob("peer_stats_*.parquet"))
        if not files:
            return {}, None
        dated = [(date.fromisoformat(p.stem.removeprefix("peer_stats_")), p) for p in files]
        eligible = [d for d in dated if d[0] <= as_of]
        chosen = max(eligible) if eligible else min(dated)
        return _load(str(chosen[1])), chosen[0].isoformat()

    @staticmethod
    def percentile(table: dict, feature: str, value: float | None, groups: list[str]) -> tuple[float | None, str | None, int]:
        """Share of peers below `value` (0..1), using the first group with a table for this feature."""
        if value is None or not np.isfinite(value):
            return None, None, 0
        for group in groups:
            entry = table.get((group, feature))
            if entry:
                n, q = entry
                # Invert the quantile function by interpolation; ties resolved at the midpoint.
                lo = np.searchsorted(q, value, side="left")
                hi = np.searchsorted(q, value, side="right")
                pct = ((lo + hi) / 2) / (len(q) - 1)
                return float(np.clip(pct, 0.0, 1.0)), group, n
        return None, None, 0
