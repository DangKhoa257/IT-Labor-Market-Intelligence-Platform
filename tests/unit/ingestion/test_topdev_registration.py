from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import pytest

from it_labor_market_intelligence.ingestion.adapters.topdev_registration import (
    BootstrapRepository,
    EnableRejected,
    PolicyState,
    SourceState,
    TopDevRegistration,
    enable_topdev,
    register_topdev,
)

NOW = datetime(2026, 7, 30, 8, 0, tzinfo=UTC)
SOURCE_ID = UUID("10000000-0000-0000-0000-000000000001")
POLICY_ID = UUID("10000000-0000-0000-0000-000000000002")


@dataclass
class _Policy:
    version: str
    reviewed: bool
    approved: bool
    notes: str


@dataclass
class _Parser:
    version: str
    active: bool
    retired_at: datetime | None = None
    configuration_hash: str | None = None
    git_commit_sha: str | None = None


class MemoryBootstrapRepository:
    def __init__(self) -> None:
        self.source: SourceState | None = None
        self.source_registration_count = 0
        self.policies: list[_Policy] = []
        self.parsers: list[_Parser] = []

    def upsert_source(self, registration: TopDevRegistration) -> SourceState:
        assert registration.slug == "topdev"
        self.source_registration_count += 1
        if self.source is None:
            self.source = SourceState(SOURCE_ID, False)
        return self.source

    def has_reviewed_policy(self, source_id: UUID) -> bool:
        assert source_id == SOURCE_ID
        return any(policy.reviewed for policy in self.policies)

    def disable_source(self, source_id: UUID, at: datetime) -> None:
        assert source_id == SOURCE_ID
        assert at == NOW
        self.source = SourceState(SOURCE_ID, False)

    def insert_default_policy(self, source_id: UUID, registration: TopDevRegistration) -> bool:
        assert source_id == SOURCE_ID
        if any(policy.version == registration.policy_version for policy in self.policies):
            return False
        self.policies.append(
            _Policy(registration.policy_version, False, False, "bootstrap default")
        )
        return True

    def current_approved_policy(self, source_id: UUID, at: datetime) -> PolicyState | None:
        assert source_id == SOURCE_ID
        assert at == NOW
        if not any(policy.approved for policy in self.policies):
            return None
        return PolicyState(POLICY_ID, 30, 30, True, True)

    def rotate_parser(
        self,
        source_id: UUID,
        registration: TopDevRegistration,
        configuration_hash: str,
        git_commit_sha: str | None,
        at: datetime,
    ) -> None:
        assert source_id == SOURCE_ID
        for parser in self.parsers:
            if parser.active and parser.version != registration.parser_version:
                parser.active = False
                parser.retired_at = at
        current = next(
            (item for item in self.parsers if item.version == registration.parser_version), None
        )
        if current is None:
            current = _Parser(registration.parser_version, True)
            self.parsers.append(current)
        current.active = True
        current.retired_at = None
        current.configuration_hash = configuration_hash
        current.git_commit_sha = git_commit_sha

    def enable_source(self, source_id: UUID, at: datetime) -> None:
        assert source_id == SOURCE_ID
        assert at == NOW
        self.source = SourceState(SOURCE_ID, True)


def test_bootstrap_is_idempotent_and_source_is_disabled_by_default() -> None:
    repository = MemoryBootstrapRepository()

    first = register_topdev(repository, git_commit_sha="ABCDEF1234567", now=NOW)
    second = register_topdev(repository, git_commit_sha="ABCDEF1234567", now=NOW)

    assert first.source_id == second.source_id == SOURCE_ID
    assert first.source_enabled is second.source_enabled is False
    assert first.policy_created is True
    assert second.policy_created is False
    assert len(repository.policies) == 1
    assert len(repository.parsers) == 1
    assert first.configuration_hash == second.configuration_hash
    assert first.git_commit_sha == "abcdef1234567"


def test_enable_is_rejected_without_approved_current_policy() -> None:
    repository = MemoryBootstrapRepository()
    result = register_topdev(repository, now=NOW)

    with pytest.raises(EnableRejected, match="approved current policy"):
        enable_topdev(repository, result.source_id, now=NOW)

    assert repository.source == SourceState(SOURCE_ID, False)


def test_reviewed_policy_is_preserved_without_bootstrap_overwrite() -> None:
    repository = MemoryBootstrapRepository()
    reviewed = _Policy("operator-reviewed-v2", True, True, "operator evidence must remain")
    repository.policies.append(reviewed)

    result = register_topdev(repository, now=NOW)

    assert result.policy_created is False
    assert repository.policies == [reviewed]
    assert repository.policies[0].notes == "operator evidence must remain"


def test_approved_policy_allows_explicit_enable() -> None:
    repository = MemoryBootstrapRepository()
    repository.policies.append(_Policy("approved-v1", True, True, "reviewed"))
    result = register_topdev(repository, now=NOW)

    enable_topdev(repository, result.source_id, now=NOW)

    assert repository.source == SourceState(SOURCE_ID, True)


def test_bootstrap_without_enable_disables_a_previously_enabled_source() -> None:
    repository = MemoryBootstrapRepository()
    repository.source = SourceState(SOURCE_ID, True)

    result = register_topdev(repository, now=NOW)

    assert result.source_enabled is False
    assert repository.source == SourceState(SOURCE_ID, False)


def test_parser_rotation_retires_previous_version_and_activates_target() -> None:
    repository = MemoryBootstrapRepository()
    repository.parsers.append(_Parser("topdev.v0", True))

    result = register_topdev(repository, git_commit_sha="1234567", now=NOW)

    assert [(item.version, item.active) for item in repository.parsers] == [
        ("topdev.v0", False),
        ("topdev.v1", True),
    ]
    assert repository.parsers[0].retired_at == NOW
    assert repository.parsers[1].configuration_hash == result.configuration_hash
    assert repository.parsers[1].git_commit_sha == "1234567"
    assert result.configuration_hash == TopDevRegistration().configuration_hash()


def test_memory_repository_satisfies_bootstrap_contract() -> None:
    repository: BootstrapRepository = MemoryBootstrapRepository()
    assert repository is not None
