"""Safety and metadata checks for Phase 1A source-verification fixtures."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "source_verification"
EXPECTED_SOURCES = {"itviec", "topdev", "glints"}
REQUIRED_METADATA_FIELDS = {
    "source",
    "source_url",
    "fetched_at",
    "http_status",
    "content_type",
    "redaction_notes",
    "evidence_type",
}
MAX_SANITIZED_FIXTURE_BYTES = 16 * 1024
FORBIDDEN_SECRET_PATTERN = re.compile(
    rb"(?i)(set-cookie\s*:|cookie\s*:|authorization\s*:|bearer\s+[a-z0-9._-]+|"
    rb"access[_-]?token|refresh[_-]?token|api[_-]?key|client[_-]?secret|"
    rb"password\s*[=:])"
)


def fixture_files() -> list[Path]:
    return [path for path in FIXTURE_ROOT.rglob("*") if path.is_file()]


def test_fixture_metadata_is_valid() -> None:
    assert {path.name for path in FIXTURE_ROOT.iterdir() if path.is_dir()} == EXPECTED_SOURCES

    metadata_files = sorted(FIXTURE_ROOT.rglob("*.metadata.json"))
    assert metadata_files

    for metadata_path in metadata_files:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert REQUIRED_METADATA_FIELDS <= metadata.keys()
        assert metadata["source"] == metadata_path.parent.name
        assert metadata["source"] in EXPECTED_SOURCES
        assert metadata["http_status"] in {200, 403}
        assert metadata["content_type"]
        assert metadata["redaction_notes"]
        assert metadata["evidence_type"]

        parsed_url = urlparse(metadata["source_url"])
        assert parsed_url.scheme == "https"
        assert parsed_url.netloc
        assert "T" in metadata["fetched_at"]


def test_every_content_fixture_has_matching_metadata() -> None:
    content_fixtures = [
        path
        for path in fixture_files()
        if not path.name.endswith(".metadata.json") and path.name != ".gitkeep"
    ]
    assert content_fixtures

    for fixture_path in content_fixtures:
        metadata_path = fixture_path.with_name(f"{fixture_path.stem}.metadata.json")
        assert metadata_path.exists(), f"Missing metadata for {fixture_path}"


def test_fixtures_contain_no_forbidden_secrets_or_cookies() -> None:
    for fixture_path in fixture_files():
        assert FORBIDDEN_SECRET_PATTERN.search(fixture_path.read_bytes()) is None, fixture_path


def test_content_fixtures_stay_below_safe_description_size() -> None:
    for fixture_path in fixture_files():
        if fixture_path.name.endswith(".metadata.json"):
            continue
        assert fixture_path.stat().st_size <= MAX_SANITIZED_FIXTURE_BYTES, fixture_path


def test_verification_documents_exist() -> None:
    for relative_path in ("docs/SOURCE_VERIFICATION.md", "docs/DATA_SCHEMA_AUDIT.md"):
        document = REPOSITORY_ROOT / relative_path
        assert document.exists()
        assert document.read_text(encoding="utf-8").strip()
