"""Internal ML-service API (ARCHITECTURE §7.2). Reachable only on the Docker network."""

from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
from datetime import date
from functools import lru_cache

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.adapters.base import CompanyRef
from app.core.config import ML_ROOT, Settings, get_settings
from app.core.jobs import RetrainJobStore
from app.core.services import get_analyzer, get_inference_log, get_services
from app.inference.analyze import Analyzer
from app.schemas.analysis import AnalysisResult, AnalyzeRequest
from pipelines.monitoring import drift

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1")


class ResolveRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=120)
    market: str = "US_SEC"
    limit: int = Field(8, ge=1, le=25)


class SentimentRequest(BaseModel):
    texts: list[str] = Field(..., min_length=1, max_length=200)


class RetrainRequest(BaseModel):
    model: str = Field(..., examples=["news_sentiment"])
    promote: bool = True


@router.post("/resolve")
def resolve(req: ResolveRequest) -> list[dict]:
    if req.market != "US_SEC":
        raise HTTPException(400, f"market {req.market} is not supported yet (US_SEC only)")
    return [c.__dict__ for c in get_services().sec.resolve(req.query, req.limit)]


@router.get("/universe")
def universe() -> list[dict]:
    """Demo universe: companies with recorded data, including historical case-study dates."""
    sec = get_services().sec
    return [{"market": "US_SEC", "market_id": f"{int(c['cik']):010d}", "ticker": c.get("ticker"), "name": c["name"],
             "role": c["role"], "as_of": c["as_of"], "case_study": c.get("case_study")} for c in sec._universe]


def _log_inference(result: AnalysisResult, analyzer: Analyzer) -> None:
    try:
        model, card = analyzer.s.registry.get("distress")
        if not result.distress.available or model is None:
            return
        snap_age = None
        fin = next((s for s in result.sources if s.source == "sec_xbrl"), None)
        if fin and fin.data_as_of:
            snap_age = (result.as_of - date.fromisoformat(fin.data_as_of)).days
        features = {f.key: f.value for p in result.pillars for f in p.factors if f.value is not None}
        features.update({d.feature: d.value for d in result.distress.drivers if d.value is not None})
        get_inference_log().append(result.company.market_id, result.as_of.isoformat(), "distress", card["version"],
                                   features, result.distress.probability_12m,
                                   {"financials_age_days": snap_age, "health": result.health.score})
    except Exception as exc:  # monitoring must never break an analysis
        log.warning("inference log failed: %s", exc)


@router.post("/analyze", response_model=AnalysisResult)
def analyze(req: AnalyzeRequest, analyzer: Analyzer = Depends(get_analyzer)) -> AnalysisResult:
    market_id = str(req.company.get("market_id", "")).strip()
    if not market_id.isdigit():
        raise HTTPException(422, "company.market_id must be a numeric SEC CIK")
    ref = CompanyRef(req.company.get("market", "US_SEC"), f"{int(market_id):010d}", req.company.get("ticker"),
                     req.company.get("name"))
    started = time.monotonic()
    try:
        result = analyzer.analyze(ref, req.as_of, req.include_backfill)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    log.info("analysed %s as of %s in %.1fs", ref.market_id, result.as_of, time.monotonic() - started)
    _log_inference(result, analyzer)
    return result


@router.post("/sentiment")
def sentiment(req: SentimentRequest) -> list[dict]:
    model, card = get_services().registry.get("news_sentiment")
    if model is None:
        raise HTTPException(503, "news_sentiment model is not trained yet")
    probs = model.predict_proba(req.texts)
    return [{"text": t, "label": ["negative", "neutral", "positive"][int(p.argmax())], "polarity": round(float(p[2] - p[0]), 4),
             "probabilities": {"negative": round(float(p[0]), 4), "neutral": round(float(p[1]), 4),
                               "positive": round(float(p[2]), 4)}, "model_version": card["version"]}
            for t, p in zip(req.texts, probs, strict=True)]


@router.get("/models")
def models() -> list[dict]:
    return get_services().registry.all_cards()


@router.get("/monitoring")
def monitoring(settings: Settings = Depends(get_settings)) -> dict:
    return drift.latest_report(settings.model_dir) or {"status": "no monitoring report yet"}


@router.post("/monitoring/run")
def run_monitoring(days: int = 30, settings: Settings = Depends(get_settings)) -> dict:
    return drift.run(settings.model_dir, settings.monitoring_db, days)


# ---------------------------------------------------------------- retraining (admin)
@lru_cache
def _job_store() -> RetrainJobStore:
    return RetrainJobStore(get_settings().monitoring_db.with_name("retrain_jobs.sqlite"))


def _require_admin(x_admin_token: str | None = Header(None), settings: Settings = Depends(get_settings)) -> None:
    if not settings.admin_token or x_admin_token != settings.admin_token:
        raise HTTPException(403, "admin token required")


def _run_training(job_id: str, model: str, promote: bool) -> None:
    store = _job_store()
    cmd = [sys.executable, "-m", "pipelines.run", model] + ([] if promote else ["--no-promote"])
    store.update(job_id, status="RUNNING", started_at=time.time())
    try:
        proc = subprocess.run(cmd, cwd=ML_ROOT, capture_output=True, text=True)
        card = get_services().registry.card(model)
        store.update(job_id, status="DONE" if proc.returncode == 0 else "FAILED", finished_at=time.time(),
                     returncode=proc.returncode, log_tail=(proc.stdout + proc.stderr)[-4000:],
                     champion_version=card.get("version") if card else None)
    except Exception as exc:  # the job record must never stay RUNNING forever
        store.update(job_id, status="FAILED", finished_at=time.time(), log_tail=repr(exc))


@router.post("/admin/retrain", dependencies=[Depends(_require_admin)], status_code=202)
def retrain(req: RetrainRequest) -> dict:
    from pipelines.run import MODELS

    if req.model not in MODELS:
        raise HTTPException(404, f"unknown model {req.model}")
    job = _job_store().create(req.model, req.promote)
    if job is None:
        raise HTTPException(409, f"{req.model} is already retraining")
    threading.Thread(target=_run_training, args=(job["id"], req.model, req.promote), daemon=True).start()
    return job


@router.get("/admin/retrain", dependencies=[Depends(_require_admin)])
def retrain_jobs() -> list[dict]:
    return _job_store().recent()
