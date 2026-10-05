"""Provider interfaces and shared types (DATA_STRATEGY §2).

Every provider returns data *or* a typed unavailable reason, plus provenance (source URLs and the
retrieval time), so a missing source lowers coverage instead of failing an analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class CompanyRef:
    market: str
    market_id: str
    ticker: str | None = None
    name: str | None = None


@dataclass
class CompanyCandidate:
    market: str
    market_id: str
    name: str
    ticker: str | None = None
    exchange: str | None = None
    former_names: list[str] = field(default_factory=list)
    match_score: float = 0.0
    is_demo: bool = False


@dataclass
class SourceResult(Generic[T]):
    data: T | None
    source: str
    retrieved_at: datetime | None = None
    urls: list[str] = field(default_factory=list)
    unavailable_reason: str | None = None
    simulated: bool = False

    @property
    def available(self) -> bool:
        return self.data is not None and self.unavailable_reason is None

    @classmethod
    def ok(cls, data: T, source: str, urls: list[str] | None = None,
           retrieved_at: datetime | None = None) -> SourceResult[T]:
        return cls(data=data, source=source, urls=urls or [], retrieved_at=retrieved_at or datetime.now(UTC))

    @classmethod
    def unavailable(cls, source: str, reason: str) -> SourceResult[T]:
        return cls(data=None, source=source, unavailable_reason=reason)


class ProviderError(RuntimeError):
    """Raised for unexpected upstream failures; callers convert it into SourceResult.unavailable."""
