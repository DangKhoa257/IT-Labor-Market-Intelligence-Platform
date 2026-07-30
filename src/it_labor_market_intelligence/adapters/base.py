"""Reusable contracts for bounded, public-source pilot adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from it_labor_market_intelligence.domain import NormalizedJobRecord

ClosedState = Literal["ACTIVE", "EXPIRED", "CLOSED", "UNKNOWN"]


@dataclass(frozen=True, slots=True)
class FetchResult:
    """One HTTP response retained in memory only while extracting a record."""

    url: str
    status: int
    body: bytes
    fetched_at: datetime
    content_type: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ClosedStateDecision:
    """Auditable evidence and comparison used for a closed-state decision."""

    state: ClosedState
    source_field: str
    raw_value: str | None
    parsed_datetime: datetime | None
    comparison_timestamp: datetime
    decision_method: str
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("closed-state confidence must be between 0 and 1")
        if self.comparison_timestamp.tzinfo is None:
            raise ValueError("closed-state comparison timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SourceRawJobRecord:
    """Source-neutral adapter output before canonical processing."""

    source: str
    source_job_id: str
    source_url: str
    title_raw: str
    source_category_raw: str | None
    discovery_method: str
    company_name_raw: str | None
    location_raw: str | None
    salary_raw: str | None
    skills_raw: tuple[str, ...] | None
    posted_at_raw: str | None
    expires_at_raw: str | None
    experience_raw: str | None
    employment_type_raw: str | None
    description_raw: str
    closed_state: ClosedState
    closed_state_provenance: ClosedStateDecision
    collected_at: datetime
    content_hash: str


class SourceAdapter(ABC):
    """Interface implemented by each separately approved source adapter."""

    @abstractmethod
    def discover_job_urls(
        self, limit: int = 30, *, request_budget: int | None = None
    ) -> tuple[str, ...]:
        """Discover at most ``limit`` unique public job-detail URLs."""

    @abstractmethod
    def fetch_job_detail(self, url: str) -> FetchResult:
        """Fetch one public job-detail URL without bypass behavior."""

    @abstractmethod
    def extract_raw_record(self, page: FetchResult) -> SourceRawJobRecord:
        """Extract source evidence into the common adapter contract."""

    @abstractmethod
    def normalize_record(self, record: SourceRawJobRecord) -> NormalizedJobRecord:
        """Run an extracted record through canonical processing."""

    @abstractmethod
    def detect_closed_state(self, page: FetchResult) -> ClosedStateDecision:
        """Detect explicit active/expired evidence, including HTTP-200 expired pages."""
