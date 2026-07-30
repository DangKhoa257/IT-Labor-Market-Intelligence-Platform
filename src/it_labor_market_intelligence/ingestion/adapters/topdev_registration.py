"""Idempotent TopDev source, policy, and parser registration."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from it_labor_market_intelligence.adapters.topdev import (
    ADAPTER_VERSION,
    TOPDEV_IT_LISTING,
    TopDevAdapter,
)

_GIT_SHA = re.compile(r"^[0-9a-fA-F]{7,64}$")


class EnableRejected(ValueError):
    """Raised when an operator requests enablement without an approved policy."""


@dataclass(frozen=True, slots=True)
class SourceState:
    id: UUID
    enabled: bool


@dataclass(frozen=True, slots=True)
class PolicyState:
    id: UUID
    maximum_requests_per_run: int
    raw_retention_days: int | None
    allow_raw_storage: bool
    allow_description_storage: bool


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    source_id: UUID
    source_enabled: bool
    policy_created: bool
    parser_version: str
    configuration_hash: str
    git_commit_sha: str | None


@dataclass(frozen=True, slots=True)
class TopDevRegistration:
    slug: str = "topdev"
    display_name: str = "TopDev"
    base_url: str = "https://topdev.vn"
    source_type: str = "job_board"
    country_code: str = "VN"
    parser_name: str = "TopDevAdapter"
    parser_version: str = ADAPTER_VERSION
    schema_version: str = "source-raw-job-record.v1"
    policy_version: str = "topdev-policy-v1"

    def configuration_payload(self) -> dict[str, object]:
        """Return stable behavior-affecting parser configuration."""

        return {
            "discovery_url": TOPDEV_IT_LISTING,
            "maximum_adapter_limit": 30,
            "parser_name": self.parser_name,
            "parser_version": self.parser_version,
            "record_schema_version": self.schema_version,
            "source_slug": self.slug,
        }

    def configuration_hash(self) -> str:
        encoded = json.dumps(
            self.configuration_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def adapter(self, transport: object | None = None) -> TopDevAdapter:
        return TopDevAdapter(transport=transport)  # type: ignore[arg-type]


class BootstrapRepository(Protocol):
    """Persistence operations required for TopDev registration."""

    def upsert_source(self, registration: TopDevRegistration) -> SourceState: ...

    def disable_source(self, source_id: UUID, at: datetime) -> None: ...

    def has_reviewed_policy(self, source_id: UUID) -> bool: ...

    def insert_default_policy(self, source_id: UUID, registration: TopDevRegistration) -> bool: ...

    def current_approved_policy(self, source_id: UUID, at: datetime) -> PolicyState | None: ...

    def rotate_parser(
        self,
        source_id: UUID,
        registration: TopDevRegistration,
        configuration_hash: str,
        git_commit_sha: str | None,
        at: datetime,
    ) -> None: ...

    def enable_source(self, source_id: UUID, at: datetime) -> None: ...


def register_topdev(
    repository: BootstrapRepository,
    *,
    registration: TopDevRegistration | None = None,
    git_commit_sha: str | None = None,
    now: datetime,
) -> BootstrapResult:
    """Register source/policy/parser without ever enabling the source."""

    definition = registration or TopDevRegistration()
    source = repository.upsert_source(definition)
    repository.disable_source(source.id, now)
    source = SourceState(source.id, False)
    policy_created = False
    if not repository.has_reviewed_policy(source.id):
        policy_created = repository.insert_default_policy(source.id, definition)

    commit_sha = _validated_git_sha(git_commit_sha)
    configuration_hash = definition.configuration_hash()
    repository.rotate_parser(
        source.id,
        definition,
        configuration_hash,
        commit_sha,
        now,
    )
    return BootstrapResult(
        source_id=source.id,
        source_enabled=source.enabled,
        policy_created=policy_created,
        parser_version=definition.parser_version,
        configuration_hash=configuration_hash,
        git_commit_sha=commit_sha,
    )


def enable_topdev(
    repository: BootstrapRepository,
    source_id: UUID,
    *,
    now: datetime,
) -> None:
    """Enable TopDev only with a currently valid fully approved policy."""

    if repository.current_approved_policy(source_id, now) is None:
        raise EnableRejected("TopDev cannot be enabled without an approved current policy")
    repository.enable_source(source_id, now)


def discover_git_commit_sha() -> str | None:
    """Return the current commit without exposing command errors or repository paths."""

    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    return _validated_git_sha(completed.stdout.strip())


def _validated_git_sha(value: str | None) -> str | None:
    if value is None:
        return None
    return value.lower() if _GIT_SHA.fullmatch(value) else None
