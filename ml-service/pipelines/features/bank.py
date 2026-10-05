"""Bank-variant financial factors (SCORING §2.2): equity, securities losses, deposits, loans, ROA."""

from __future__ import annotations

import numpy as np

from pipelines.features.financial import Snapshot, _div

BANK_FEATURES = ["equity_assets", "securities_loss_equity", "deposit_growth", "loans_deposits", "bank_roa"]


def bank_features(snap: Snapshot) -> dict[str, float]:
    f = dict.fromkeys(BANK_FEATURES, np.nan)
    if snap.period_end is None:
        return f
    v, p = snap.values, snap.prev
    f["equity_assets"] = _div(v["StockholdersEquity"], v["TotalAssets"])
    losses = 0.0
    found = False
    for cost, fair in (("HtmAmortizedCost", "HtmFairValue"), ("AfsAmortizedCost", "AfsFairValue")):
        if not (np.isnan(v.get(cost, np.nan)) or np.isnan(v.get(fair, np.nan))):
            losses += max(0.0, v[cost] - v[fair])  # unrealised loss = amortised cost - fair value
            found = True
    f["securities_loss_equity"] = _div(losses, v["StockholdersEquity"]) if found else np.nan
    f["deposit_growth"] = _div(v["Deposits"], p["Deposits"]) - 1 if p.get("Deposits") else np.nan
    f["loans_deposits"] = _div(v["Loans"], v["Deposits"])
    f["bank_roa"] = _div(v["NetIncome"], v["TotalAssets"])
    return f
