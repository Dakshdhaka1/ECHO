"""`AnalysisResult` - the versioned contract between the ML service and the backend (ARCHITECTURE §7.3)."""

from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"
Kind = Literal["ML", "Stat", "Rule"]
Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
DISCLAIMER = ("ECHO reports observable public signals and model estimates. It is not financial advice and does not "
              "predict with certainty whether a company will succeed or fail.")


class CompanyInfo(BaseModel):
    market: str
    market_id: str
    name: str
    legal_name: str | None = None
    ticker: str | None = None
    exchange: str | None = None
    sic: str | None = None
    sic_description: str | None = None
    sector: str
    is_bank: bool = False
    former_names: list[str] = []
    fiscal_year_end: str | None = None


class CaseStudy(BaseModel):
    as_of: dt.date
    note: str


class Factor(BaseModel):
    key: str
    label: str
    kind: Kind
    value: float | None
    display_value: str | None = None
    score: float | None
    peer_percentile: float | None = None
    peer_group: str | None = None
    weight: float
    impact: float = 0.0
    direction: Literal["higher_is_better", "lower_is_better", "penalty"] = "higher_is_better"
    note: str | None = None
    evidence: list[str] = []


class Pillar(BaseModel):
    key: str
    label: str
    score: float | None
    weight: float
    effective_weight: float
    coverage: float
    unavailable_reason: str | None = None
    factors: list[Factor] = []


class Health(BaseModel):
    score: int | None
    band: str
    confidence: float
    raw_score: float | None = None
    override: str | None = None


class Driver(BaseModel):
    feature: str
    label: str
    value: float | None
    contribution: float


class Distress(BaseModel):
    available: bool
    probability_12m: float | None = None
    risk_band: str | None = None
    model: str | None = None
    base_rate: float | None = None
    drivers: list[Driver] = []
    unavailable_reason: str | None = None
    kind: Kind = "ML"


class Segment(BaseModel):
    available: bool
    segment: str | None = None
    membership: float | None = None
    description: str | None = None
    model: str | None = None
    unavailable_reason: str | None = None


class Signal(BaseModel):
    code: str
    severity: Severity
    kind: Kind
    date: dt.date | None = None
    message: str
    evidence: list[str] = []


class Event(BaseModel):
    id: str
    date: dt.date
    type: str
    label: str
    origin: str
    severity: Severity
    title: str
    penalty: float = 0.0
    sentiment: float | None = None
    evidence: list[str] = []


class Anomaly(BaseModel):
    date: dt.date
    series: str
    score: float
    kind: Kind = "ML"
    note: str
    model: str | None = None


class ForecastPoint(BaseModel):
    horizon: int
    period_end: dt.date
    p10: float
    p50: float
    p90: float


class Forecast(BaseModel):
    series: str
    model: str
    unit: str = "USD"
    history: list[dict] = []
    points: list[ForecastPoint] = []


class EmployeeSentiment(BaseModel):
    available: bool
    index: float | None = None
    ci90: list[float] | None = None
    as_of_quarter: str | None = None
    reviews: int | None = None
    themes: list[dict] = []
    series: list[dict] = []
    unavailable_reason: str | None = None


class NewsSummary(BaseModel):
    available: bool
    articles: int = 0
    mean_sentiment: float | None = None
    positive_share: float | None = None
    negative_share: float | None = None
    headlines: list[dict] = []
    unavailable_reason: str | None = None


class EvidenceItem(BaseModel):
    type: str
    title: str
    url: str | None = None
    date: dt.date | None = None
    source: str | None = None


class SourceStatus(BaseModel):
    source: str
    available: bool
    retrieved_at: str | None = None
    data_as_of: str | None = None
    reason: str | None = None
    replayed: bool = False


class Summary(BaseModel):
    text: str
    pillar_notes: dict[str, str] = {}
    key_risks: list[dict] = []
    generator: str
    grounding_check: str


class AnalysisResult(BaseModel):
    schema_version: str = SCHEMA_VERSION
    model_version: str
    company: CompanyInfo
    case_study: CaseStudy | None = None
    as_of: dt.date
    generated_at: str
    health: Health
    pillars: list[Pillar]
    distress: Distress
    segment: Segment
    signals: list[Signal] = []
    events: list[Event] = []
    anomalies: list[Anomaly] = []
    forecasts: list[Forecast] = []
    employee: EmployeeSentiment
    news: NewsSummary
    timeseries: dict[str, list[dict]] = {}
    history: list[dict] = []
    evidence: dict[str, EvidenceItem] = {}
    sources: list[SourceStatus] = []
    models: dict[str, str] = {}
    summary: Summary
    disclaimer: str = DISCLAIMER


class AnalyzeRequest(BaseModel):
    company: dict = Field(..., examples=[{"market": "US_SEC", "market_id": "0000320193"}])
    as_of: dt.date | None = None
    include_backfill: bool = True
