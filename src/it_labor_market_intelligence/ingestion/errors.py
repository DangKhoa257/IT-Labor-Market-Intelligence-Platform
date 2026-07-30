"""Bounded ingestion error and retry classification."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RetryDecision:
    retryable: bool
    delay_seconds: int | None


def retry_decision(
    http_status: int | None, attempt: int, retry_after: int | None = None
) -> RetryDecision:
    if http_status in {400, 401, 403, 404, 410} or attempt >= 3:
        return RetryDecision(False, None)
    if http_status is None or http_status in {408, 425, 429, 500, 502, 503, 504}:
        return RetryDecision(
            True,
            (
                min(retry_after, 300)
                if retry_after and retry_after > 0
                else (5 if attempt == 1 else 30)
            ),
        )
    return RetryDecision(False, None)
