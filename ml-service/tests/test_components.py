"""Grounding validator, split adjustment, drift PSI, news de-duplication and event rules."""

import numpy as np
import pandas as pd

from app.adapters.news import deduplicate
from app.core.jobs import RetrainJobStore
from app.adapters.prices import adjust_splits
from app.inference.explain import grounding_check
from app.inference.news_events import classify
from pipelines.monitoring.drift import psi, reference_histogram


def test_grounding_rejects_invented_numbers_and_advice():
    facts = {"health": {"score": 71, "confidence": 0.78}, "pillars": [{"score": 82.5}]}
    ok = {"summary": "Score 71 with 78% coverage; financial pillar 82.5.", "pillar_notes": {}, "key_risks": []}
    assert grounding_check(ok, facts, set()) == []
    bad = {"summary": "Score 71 but revenue will grow 37.2% so you should buy.", "pillar_notes": {},
           "key_risks": [{"text": "x", "evidence_ids": ["ev:missing"]}]}
    problems = grounding_check(bad, facts, {"ev:ok"})
    assert any("37.2" in p for p in problems)
    assert any("unknown evidence id" in p for p in problems)
    assert any("advice" in p for p in problems)


def test_split_adjustment_removes_artificial_crash():
    idx = pd.date_range("2024-01-01", periods=6, freq="B")
    px = pd.DataFrame({"open": [100, 101, 102, 25.6, 26, 26.5], "high": [101, 102, 103, 26, 27, 27],
                       "low": [99, 100, 101, 25, 25.5, 26], "close": [100, 101, 102.4, 25.8, 26.4, 26.6],
                       "volume": [1e6, 1e6, 1e6, 4e6, 4e6, 4e6]}, index=idx)
    adj, splits = adjust_splits(px)
    assert splits == [{"date": idx[3].date().isoformat(), "ratio": "4:1"}]
    assert abs(adj["close"].iloc[2] - 25.6) < 1e-9
    assert np.abs(np.log(adj["close"]).diff().dropna()).max() < 0.05


def test_psi_is_zero_for_same_distribution_and_large_for_shift():
    rng = np.random.default_rng(0)
    ref = reference_histogram(pd.Series(rng.normal(size=5000)))
    assert psi(ref, rng.normal(size=5000)) < 0.02
    assert psi(ref, rng.normal(loc=1.5, size=5000)) > 0.2


def test_deduplicate_syndicated_headlines():
    ts = pd.Timestamp("2026-09-01", tz="UTC")
    df = pd.DataFrame({"title": ["Apple beats estimates on iPhone demand", "Apple beats estimates on iPhone demand!",
                                 "Apple Beats Estimates On iPhone Demand - Reuters", "Apple faces EU probe"],
                       "url": list("abcd"), "domain": list("abcd"), "published_at": [ts] * 4, "source_country": [""] * 4})
    assert len(deduplicate(df)) == 2


def test_news_event_rules():
    assert classify("Intel to cut 15,000 jobs in restructuring")[0] == "LAYOFFS"
    assert classify("Boeing sued by shareholders in class action")[0] == "LEGAL_REGULATORY"
    assert classify("Apple unveils new iPhone") is None


def test_retrain_job_store_deduplicates_across_processes(tmp_path):
    a, b = RetrainJobStore(tmp_path / "j.sqlite"), RetrainJobStore(tmp_path / "j.sqlite")  # two "workers"
    job = a.create("distress", True)
    assert job["status"] == "QUEUED" and b.create("distress", True) is None
    b.update(job["id"], status="DONE")
    assert a.recent()[-1]["status"] == "DONE" and a.create("distress", True) is not None
