"""TopDev adapter tests use sanitized fixtures and synthetic wrappers only."""

from __future__ import annotations

import json
import shutil
import subprocess
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from email.message import Message
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest

from it_labor_market_intelligence.adapters import FetchResult, TopDevAdapter
from it_labor_market_intelligence.adapters.topdev import (
    TOPDEV_IT_LISTING,
    PoliteCurlTransport,
    PoliteUrllibTransport,
    extract_job_id,
)
from it_labor_market_intelligence.ingestion.runner import url_allowed_by_policy

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures" / "source_verification" / "topdev"
FETCHED_AT = datetime(2026, 7, 24, tzinfo=UTC)


def _html_page(fixture_name: str, **overrides: object) -> bytes:
    posting = json.loads((FIXTURES / fixture_name).read_text(encoding="utf-8"))
    posting["description"] = (
        "SYNTHETIC_TEST_DATA / EXAMPLE_NOT_REAL_DATA. "
        "Required experience with Java and Spring Boot."
    )
    posting.update(overrides)
    return (
        '<html><script type="application/ld+json">'
        + json.dumps(posting, ensure_ascii=False)
        + "</script></html>"
    ).encode()


def _page(fixture_name: str, job_id: str, **overrides: object) -> FetchResult:
    return FetchResult(
        url=f"https://topdev.vn/viec-lam/synthetic-job-{job_id}",
        status=200,
        body=_html_page(fixture_name, **overrides),
        fetched_at=FETCHED_AT,
        content_type="text/html; charset=utf-8",
    )


def _state_page(
    valid_through: str | None,
    *,
    fetched_at: datetime,
    prefix: str = "",
    suffix: str = "",
) -> FetchResult:
    posting: dict[str, object] = {"@context": "https://schema.org", "@type": "JobPosting"}
    if valid_through is not None:
        posting["validThrough"] = valid_through
    body = (
        prefix
        + '<script type="application/ld+json">'
        + json.dumps(posting, ensure_ascii=False)
        + "</script>"
        + suffix
    ).encode()
    return FetchResult(
        url="https://topdev.vn/viec-lam/synthetic-state-999",
        status=200,
        body=body,
        fetched_at=fetched_at,
        content_type="text/html",
    )


def _mapping_transport(responses: dict[str, FetchResult]) -> Callable[[str], FetchResult]:
    return responses.__getitem__


def test_url_discovery_deduplicates_and_obeys_limit() -> None:
    jobs = [f"https://topdev.vn/viec-lam/synthetic-{number}" for number in range(100, 135)]
    listing_html = (
        '<a href="/companies/not-a-job-999">Company</a>'
        '<a href="/viec-lam/tim-kiem">Listing</a>'
        + "".join(f'<a href="{url}?src=listing">Job</a>' for url in [jobs[0], jobs[0], *jobs[1:]])
    ).encode()
    adapter = TopDevAdapter(
        _mapping_transport(
            {
                TOPDEV_IT_LISTING: FetchResult(TOPDEV_IT_LISTING, 200, listing_html, FETCHED_AT),
            }
        )
    )
    discovered = adapter.discover_job_urls(limit=30)
    assert len(discovered) == 30
    assert len(set(discovered)) == 30
    assert discovered[0] == jobs[0]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://topdev.vn/detail-jobs/java-developer-company-2121360", "2121360"),
        ("https://topdev.vn/viec-lam/backend-engineer-2086809", "2086809"),
    ],
)
def test_job_id_is_extracted_from_url(url: str, expected: str) -> None:
    assert extract_job_id(url) == expected


def test_json_ld_parsing_uses_url_id_not_company_identifier() -> None:
    adapter = TopDevAdapter()
    raw = adapter.extract_raw_record(_page("job_2121360.json", "2121360"))
    assert raw.source_job_id == "2121360"
    assert raw.source_job_id != "78272"
    assert raw.title_raw == "Java Developer"
    assert raw.source_category_raw is None
    assert raw.discovery_method == "topdev_it_listing_html"
    assert raw.company_name_raw == "DTN E-COMMERCE SOFTWARE COMPANY LIMITED"
    assert raw.experience_raw == "minimum 24 months"
    assert raw.employment_type_raw == "OTHER"
    assert len(raw.content_hash) == 64


def test_negotiable_salary_ignores_misleading_currency_metadata() -> None:
    adapter = TopDevAdapter()
    raw = adapter.extract_raw_record(_page("job_2121362.json", "2121362"))
    normalized = adapter.normalize_record(raw)
    assert raw.salary_raw == "Negotiable"
    assert normalized.salary.disclosed is False
    assert normalized.salary.minimum is None and normalized.salary.maximum is None
    assert normalized.salary.currency is None


def test_salary_range_string_and_month_experience_normalize() -> None:
    adapter = TopDevAdapter()
    raw = adapter.extract_raw_record(_page("job_2121360.json", "2121360"))
    normalized = adapter.normalize_record(raw)
    assert normalized.salary.minimum == Decimal("15000000")
    assert normalized.salary.maximum == Decimal("25000000")
    assert normalized.salary.currency == "VND"
    assert normalized.salary.period == "month"
    assert normalized.salary.salary_type is None
    assert normalized.experience.minimum_years == Decimal(2)
    assert normalized.experience.maximum_years is None


def test_employment_type_other_is_preserved_as_raw_only() -> None:
    raw = TopDevAdapter().extract_raw_record(_page("job_2121361.json", "2121361"))
    assert raw.employment_type_raw == "OTHER"


def test_source_industry_is_extracted_for_scope_classification() -> None:
    raw = TopDevAdapter().extract_raw_record(
        _page("job_2121360.json", "2121360", industry="Information Technology")
    )
    assert raw.source_category_raw == "Information Technology"


def test_expired_http_200_page_is_detected() -> None:
    page = FetchResult(
        url=("https://topdev.vn/viec-lam/software-engineer-middle-senior-nodejs-2086809"),
        status=200,
        body=(FIXTURES / "job_2086809.html").read_bytes(),
        fetched_at=FETCHED_AT,
        content_type="text/html",
    )
    decision = TopDevAdapter().detect_closed_state(page)
    assert decision.state == "CLOSED"
    assert decision.source_field == "html:data-job-state"
    assert decision.raw_value == "closed"
    assert decision.decision_method == "explicit_job_state_marker"


def test_future_valid_through_is_active_with_provenance() -> None:
    decision = TopDevAdapter().detect_closed_state(
        _state_page("2026-07-25", fetched_at=datetime(2026, 7, 24, 12, tzinfo=UTC))
    )
    assert decision.state == "ACTIVE"
    assert decision.source_field == "jsonld.validThrough"
    assert decision.raw_value == "2026-07-25"
    assert decision.parsed_datetime is not None
    assert decision.parsed_datetime.utcoffset() is not None
    assert decision.comparison_timestamp.utcoffset() is not None
    assert decision.decision_method == "inclusive_valid_through_comparison"
    assert decision.confidence == 0.98


def test_past_valid_through_is_expired() -> None:
    decision = TopDevAdapter().detect_closed_state(
        _state_page("2026-07-23", fetched_at=datetime(2026, 7, 24, 12, tzinfo=UTC))
    )
    assert decision.state == "EXPIRED"


def test_date_only_valid_through_is_inclusive_for_current_vietnam_date() -> None:
    decision = TopDevAdapter().detect_closed_state(
        _state_page("2026-07-24", fetched_at=datetime(2026, 7, 24, 16, tzinfo=UTC))
    )
    assert decision.state == "ACTIVE"
    assert decision.parsed_datetime is not None
    assert decision.parsed_datetime.hour == 23


def test_timezone_offset_valid_through_compares_absolute_instants() -> None:
    decision = TopDevAdapter().detect_closed_state(
        _state_page(
            "2026-07-24T20:00:00+07:00",
            fetched_at=datetime(2026, 7, 24, 12, tzinfo=UTC),
        )
    )
    assert decision.state == "ACTIVE"
    assert decision.comparison_timestamp.hour == 19


def test_utc_z_valid_through_is_parsed_as_aware_datetime() -> None:
    decision = TopDevAdapter().detect_closed_state(
        _state_page(
            "2026-07-24T12:00:00Z",
            fetched_at=datetime(2026, 7, 24, 11, tzinfo=UTC),
        )
    )
    assert decision.state == "ACTIVE"
    assert decision.parsed_datetime is not None
    assert decision.parsed_datetime.tzinfo == UTC


@pytest.mark.parametrize("valid_through", [None, "not-a-date"])
def test_missing_or_malformed_valid_through_is_unknown(valid_through: str | None) -> None:
    decision = TopDevAdapter().detect_closed_state(
        _state_page(valid_through, fetched_at=datetime(2026, 7, 24, tzinfo=UTC))
    )
    assert decision.state == "UNKNOWN"
    assert decision.parsed_datetime is None
    assert decision.confidence == 0.0


def test_explicit_expired_marker_overrides_future_valid_through() -> None:
    decision = TopDevAdapter().detect_closed_state(
        _state_page(
            "2026-08-24",
            fetched_at=datetime(2026, 7, 24, tzinfo=UTC),
            prefix='<main data-job-state="expired">',
            suffix="</main>",
        )
    )
    assert decision.state == "EXPIRED"
    assert decision.decision_method == "explicit_job_state_marker"


def test_translation_catalog_expired_text_does_not_override_valid_through() -> None:
    decision = TopDevAdapter().detect_closed_state(
        _state_page(
            "2026-08-24",
            fetched_at=datetime(2026, 7, 24, tzinfo=UTC),
            prefix='<script>window.messages={"detail_job_page_expired":"Đã hết hạn"}</script>',
        )
    )
    assert decision.state == "ACTIVE"


def test_explicit_active_application_state_is_used_after_missing_date() -> None:
    decision = TopDevAdapter().detect_closed_state(
        _state_page(
            None,
            fetched_at=datetime(2026, 7, 24, tzinfo=UTC),
            prefix='<main data-application-state="active">',
            suffix="</main>",
        )
    )
    assert decision.state == "ACTIVE"
    assert decision.decision_method == "explicit_active_application_state"


def test_optional_missing_fields_remain_null() -> None:
    page = _page(
        "job_2121360.json",
        "2121360",
        baseSalary=None,
        skills=None,
        experienceRequirements=None,
        jobLocation=None,
        employmentType=None,
    )
    raw = TopDevAdapter().extract_raw_record(page)
    normalized = TopDevAdapter().normalize_record(raw)
    assert raw.salary_raw is None
    assert raw.skills_raw is None
    assert raw.experience_raw is None
    assert raw.location_raw is None
    assert raw.employment_type_raw is None
    assert normalized.salary.currency is None
    assert normalized.experience.minimum_years is None


def test_missing_required_json_ld_fields_rejects_record() -> None:
    page = _page("job_2121360.json", "2121360", title=None)
    with pytest.raises(ValueError, match="Required title/description missing"):
        TopDevAdapter().extract_raw_record(page)


class _MockHTTPResponse:
    def __init__(
        self,
        url: str,
        status: int,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes = b"body",
    ) -> None:
        self._url = url
        self.status = status
        self.headers = dict(headers or {})
        self._body = body
        self.closed = False

    def geturl(self) -> str:
        return self._url

    def read(self) -> bytes:
        return self._body

    def close(self) -> None:
        self.closed = True


class _MockOpener:
    def __init__(self, responses: Mapping[str, _MockHTTPResponse | HTTPError]) -> None:
        self.responses = dict(responses)
        self.calls: list[str] = []

    def open(self, request: urllib.request.Request, timeout: int) -> _MockHTTPResponse:
        del timeout
        url = str(request.full_url)
        self.calls.append(url)
        response = self.responses[url]
        if isinstance(response, HTTPError):
            raise response
        return response


def _urllib_transport(
    monkeypatch: pytest.MonkeyPatch,
    opener: _MockOpener,
) -> PoliteUrllibTransport:
    monkeypatch.setattr(urllib.request, "build_opener", lambda *args: opener)
    transport = PoliteUrllibTransport(minimum_interval_seconds=0)

    def validate_path(url: str) -> None:
        if not url_allowed_by_policy(
            url,
            ("/viec-lam/*",),
            ("/viec-lam/blocked/*",),
        ):
            raise ValueError("redirect path rejected")

    transport.set_redirect_validator(validate_path)
    return transport


def test_urllib_transport_exposes_only_safe_http_error_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = Message()
    headers["Content-Type"] = "text/html"
    headers["ETag"] = '"fixture-etag"'
    headers["Last-Modified"] = "Wed, 29 Jul 2026 10:00:00 GMT"
    headers["Retry-After"] = "17"
    headers["Set-Cookie"] = "session=SECRET"
    error = HTTPError(
        "https://topdev.vn/viec-lam/fixture-429",
        429,
        "rate limited",
        headers,
        BytesIO(b"rate limited"),
    )

    opener = _MockOpener({error.url: error})
    response = _urllib_transport(monkeypatch, opener)(error.url)

    assert response.status == 429
    assert response.headers["ETag"] == '"fixture-etag"'
    assert response.headers["Last-Modified"] == "Wed, 29 Jul 2026 10:00:00 GMT"
    assert response.headers["Retry-After"] == "17"
    assert "Set-Cookie" not in response.headers


@pytest.mark.parametrize(
    ("location", "final_url"),
    [
        (
            "https://www.topdev.vn/viec-lam/approved-final-2",
            "https://www.topdev.vn/viec-lam/approved-final-2",
        ),
        ("/viec-lam/approved-relative-3", "https://topdev.vn/viec-lam/approved-relative-3"),
    ],
    ids=("approved-www-host", "approved-relative"),
)
def test_urllib_transport_follows_only_validated_redirects(
    monkeypatch: pytest.MonkeyPatch, location: str, final_url: str
) -> None:
    initial = "https://topdev.vn/viec-lam/approved-start-1"
    opener = _MockOpener(
        {
            initial: _MockHTTPResponse(initial, 302, headers={"Location": location}),
            final_url: _MockHTTPResponse(
                final_url,
                200,
                headers={"ETag": '"redirect-final"', "Set-Cookie": "SECRET"},
            ),
        }
    )

    response = _urllib_transport(monkeypatch, opener)(initial)

    assert opener.calls == [initial, final_url]
    assert response.url == final_url
    assert response.headers == {"ETag": '"redirect-final"'}


@pytest.mark.parametrize(
    "location",
    [
        "https://example.com/viec-lam/approved-2",
        "http://topdev.vn/viec-lam/approved-2",
        "https://topdev.vn/viec-lam/blocked/secret-2",
        "https://topdev.vn/companies/unapproved-2",
    ],
    ids=("cross-host", "http-downgrade", "blocked-path", "unapproved-path"),
)
def test_urllib_transport_rejects_redirect_before_forbidden_target_call(
    monkeypatch: pytest.MonkeyPatch, location: str
) -> None:
    initial = "https://topdev.vn/viec-lam/approved-start-1"
    opener = _MockOpener({initial: _MockHTTPResponse(initial, 302, headers={"Location": location})})

    with pytest.raises((ValueError, OSError)):
        _urllib_transport(monkeypatch, opener)(initial)

    assert opener.calls == [initial]
    assert location not in opener.calls


def test_urllib_transport_rejects_redirect_loop_without_second_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = "https://topdev.vn/viec-lam/approved-loop-1"
    opener = _MockOpener({initial: _MockHTTPResponse(initial, 302, headers={"Location": initial})})

    with pytest.raises(OSError, match="loop"):
        _urllib_transport(monkeypatch, opener)(initial)

    assert opener.calls == [initial]


def test_urllib_transport_rejects_more_than_three_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    urls = [f"https://topdev.vn/viec-lam/approved-hop-{number}" for number in range(5)]
    opener = _MockOpener(
        {
            url: _MockHTTPResponse(url, 302, headers={"Location": urls[index + 1]})
            for index, url in enumerate(urls[:-1])
        }
    )

    with pytest.raises(OSError, match="limit"):
        _urllib_transport(monkeypatch, opener)(urls[0])

    assert opener.calls == urls[:4]
    assert urls[4] not in opener.calls


def test_curl_transport_exposes_allowlisted_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: "curl")
    header_json = json.dumps(
        {
            "content-type": "text/html",
            "etag": ['"curl-etag"'],
            "last-modified": "Wed, 29 Jul 2026 11:00:00 GMT",
            "retry-after": "23",
            "x-csrf-token": "SECRET",
        }
    )
    stdout = (
        b"body\n__TOPDEV_PILOT_META__200\thttps://topdev.vn/viec-lam/curl-123"
        + b"\ttext/html\t"
        + header_json.encode()
    )
    completed = subprocess.CompletedProcess(["curl"], 0, stdout=stdout, stderr=b"")
    commands: list[list[str]] = []

    def run_curl(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        del kwargs
        commands.append(command)
        return completed

    monkeypatch.setattr(subprocess, "run", run_curl)

    response = PoliteCurlTransport(minimum_interval_seconds=0)(
        "https://topdev.vn/viec-lam/curl-123"
    )

    assert response.headers == {
        "content-type": "text/html",
        "etag": '"curl-etag"',
        "last-modified": "Wed, 29 Jul 2026 11:00:00 GMT",
        "retry-after": "23",
    }
    assert "--location" not in commands[0]


@pytest.mark.parametrize(
    ("returncode", "metadata", "expected_exception", "message"),
    [
        (28, b"000\thttps://topdev.vn/viec-lam/curl-123\t\t{}", TimeoutError, "timed out"),
        (6, b"", OSError, "transport failed"),
        (0, b"missing-fields", OSError, "metadata is malformed"),
        (0, b"abc\thttps://topdev.vn/viec-lam/curl-123\ttext/html\t{}", OSError, "status"),
        (0, b"000\thttps://topdev.vn/viec-lam/curl-123\ttext/html\t{}", OSError, "valid HTTP"),
        (
            0,
            b"200\thttps://topdev.vn/viec-lam/curl-123\ttext/html\t{bad",
            OSError,
            "header metadata",
        ),
    ],
    ids=(
        "timeout-status-000",
        "dns-connect-failure",
        "malformed-metadata",
        "malformed-status",
        "status-000",
        "malformed-header-json",
    ),
)
def test_curl_transport_rejects_untrustworthy_failures(
    monkeypatch: pytest.MonkeyPatch,
    returncode: int,
    metadata: bytes,
    expected_exception: type[Exception],
    message: str,
) -> None:
    monkeypatch.setattr(shutil, "which", lambda _: "curl")
    marker = b"\n__TOPDEV_PILOT_META__"
    stdout = b"PRIVATE_BODY" + marker + metadata if metadata else b""
    completed = subprocess.CompletedProcess(
        ["curl"],
        returncode,
        stdout=stdout,
        stderr=b"proxy=http://user:password@example.test token=SECRET",
    )
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: completed)

    with pytest.raises(expected_exception, match=message) as error:
        PoliteCurlTransport(minimum_interval_seconds=0)("https://topdev.vn/viec-lam/curl-123")

    rendered = str(error.value)
    assert "SECRET" not in rendered
    assert "password" not in rendered
    assert "PRIVATE_BODY" not in rendered
