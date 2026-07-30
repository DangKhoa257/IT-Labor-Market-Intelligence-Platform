"""Source-independent contracts used by ingestion orchestration.

The adapters package predates the database-backed ingestion worker and exposes
an abstract base class which also includes canonical normalization.  Ingestion
stops before canonical processing, so the worker uses the smaller structural
protocol in this module instead of depending on that unrelated method.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from it_labor_market_intelligence.adapters.base import (
    ClosedStateDecision,
    FetchResult,
    SourceRawJobRecord,
)

type JsonScalar = None | bool | int | float | str
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]
type JsonContainer = list[JsonValue] | dict[str, JsonValue]

# The ingestion specification calls this value ``FetchResponse``.  Keep the
# adapter's established concrete type as the single response representation.
FetchResponse = FetchResult
RawRecord = SourceRawJobRecord


@runtime_checkable
class IngestionAdapter(Protocol):
    """The source-facing behavior required by the ingestion worker."""

    source_slug: str
    parser_name: str
    parser_version: str
    record_schema_version: str

    def discover_job_urls(self, limit: int = 30) -> Sequence[str]:
        """Return at most ``limit`` validated source detail URLs."""

    def fetch_job_detail(self, url: str) -> FetchResponse:
        """Fetch one validated public detail URL."""

    def extract_raw_record(self, page: FetchResponse) -> RawRecord:
        """Extract direct source evidence without canonical classification."""

    def detect_closed_state(self, page: FetchResponse) -> ClosedStateDecision:
        """Return the source evidence used to determine closed state."""


class FetchTransport(Protocol):
    """Injectable GET transport used by source adapters."""

    def __call__(self, url: str) -> FetchResponse:
        """Fetch ``url`` and return an in-memory response."""


class Clock(Protocol):
    """Injectable timezone-aware wall clock."""

    def now(self) -> datetime:
        """Return the current timezone-aware timestamp."""


class RetryScheduler(Protocol):
    """Injectable retry-delay policy; implementations must never sleep."""

    def delay_seconds(self, attempt_number: int, retry_after: str | None = None) -> int | None:
        """Return a bounded delay, or ``None`` when no retry is allowed."""


@dataclass(frozen=True, slots=True)
class FixtureResponse:
    """A deterministic transport response backed by repository fixtures."""

    url: str
    status: int
    body: bytes
    fetched_at: datetime
    content_type: str | None = "text/html"
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.url:
            raise ValueError("fixture response URL must not be blank")
        if not 100 <= self.status <= 599:
            raise ValueError("fixture response status must be between 100 and 599")
        if self.fetched_at.tzinfo is None or self.fetched_at.utcoffset() is None:
            raise ValueError("fixture response fetched_at must be timezone-aware")

    def as_fetch_result(self) -> FetchResult:
        """Convert to the response type consumed by existing adapters."""

        return FetchResult(
            url=self.url,
            status=self.status,
            body=self.body,
            fetched_at=self.fetched_at,
            content_type=self.content_type,
            headers=dict(self.headers),
        )
