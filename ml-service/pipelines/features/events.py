"""Canonical events from SEC filings (M2b, Kind = Rule) and point-in-time event features."""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipelines.common import load_mapping

DECAY_DAYS = 180.0
WINDOW_DAYS = 365

# Event types used as model features (BANKRUPTCY is the distress label, so it is never a feature).
EVENT_FEATURES = {
    "RESTATEMENT": "ev_restatement",
    "AUDITOR_CHANGE": "ev_auditor_change",
    "EXEC_DEPARTURE": "ev_exec_departure",
    "RESTRUCTURING": "ev_restructuring",
    "IMPAIRMENT": "ev_impairment",
    "DELISTING_NOTICE": "ev_delisting_notice",
    "DEBT_ACCELERATION": "ev_debt_acceleration",
    "LATE_FILING": "ev_late_filing",
    "CYBER_INCIDENT": "ev_cyber_incident",
}

EVENT_COLUMNS = ["cik", "filed", "accn", "source", "event", "label", "penalty", "severity", "cap"]


def canonical_events(filings: pd.DataFrame) -> pd.DataFrame:
    """Map 8-K item codes and event-forms to ECHO's event taxonomy (mappings/sec_8k_items.yaml)."""
    mapping = load_mapping("sec_8k_items.yaml")
    rows = []
    eight_k = filings[filings["form"].str.startswith("8-K") & filings["items"].fillna("").ne("")]
    for cik, filed, accn, items in zip(eight_k["cik"], eight_k["filed"], eight_k["accn"], eight_k["items"],
                                       strict=True):
        for code in {c.strip() for c in str(items).split(",")}:
            spec = mapping["items"].get(code)
            if spec:
                rows.append((cik, filed, accn, f"8-K Item {code}", spec["event"], spec["label"], spec["penalty"],
                             spec["severity"], spec.get("cap")))
    for form, spec in mapping["forms"].items():
        hits = filings[filings["form"] == form]
        rows.extend((c, f, a, form, spec["event"], spec["label"], spec["penalty"], spec["severity"], spec.get("cap"))
                    for c, f, a in zip(hits["cik"], hits["filed"], hits["accn"], strict=True))
    events = pd.DataFrame(rows, columns=EVENT_COLUMNS)
    return events.sort_values(["cik", "filed"]).reset_index(drop=True)


def event_features(events: pd.DataFrame, as_of: pd.Timestamp) -> dict[str, float]:
    """Decayed event counts over the 12 months before `as_of` (only events filed on or before as_of)."""
    feats = dict.fromkeys(EVENT_FEATURES.values(), 0.0)
    if events.empty:
        return feats
    age = (as_of - events["filed"]).dt.days
    recent = events[(age >= 0) & (age <= WINDOW_DAYS)]
    for event, a in zip(recent["event"], age[recent.index], strict=True):
        name = EVENT_FEATURES.get(event)
        if name:
            feats[name] += float(np.exp(-a / DECAY_DAYS))
    return feats
