"""Source adapter contracts and approved pilot implementations."""

from .base import ClosedStateDecision, FetchResult, SourceAdapter, SourceRawJobRecord
from .topdev import TopDevAdapter

__all__ = [
    "ClosedStateDecision",
    "FetchResult",
    "SourceAdapter",
    "SourceRawJobRecord",
    "TopDevAdapter",
]
