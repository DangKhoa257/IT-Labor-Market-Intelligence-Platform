"""Low-volume TopDev public job adapter using JSON-LD ``JobPosting`` evidence."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta, timezone
from datetime import time as datetime_time
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

from it_labor_market_intelligence.domain import NormalizedJobRecord, RawJobRecord
from it_labor_market_intelligence.processing import normalize_job_record

from .base import ClosedStateDecision, FetchResult, SourceAdapter, SourceRawJobRecord

ADAPTER_VERSION = "topdev.v1"
TOPDEV_IT_LISTING = "https://topdev.vn/viec-lam/tim-kiem"
DISCOVERY_METHOD = "topdev_it_listing_html"
USER_AGENT = (
    "VietnamITLaborMarketIntelligence-TopDevPilot/1.0 (low-volume public research; max 30 records)"
)
_JOB_ID = re.compile(r"(?:-|/)(\d+)(?:[/?#]|$)")
_EXPLICIT_JOB_STATE = re.compile(
    r"data-job-state\s*=\s*['\"](?P<state>expired|closed)['\"]", re.IGNORECASE
)
_ACTIVE_APPLICATION_STATE = re.compile(
    r"data-application-state\s*=\s*['\"](?P<state>active|open|accepting)['\"]",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE = re.compile(r"(?<!\d)(?:\+?84|0)(?:[ .-]?\d){8,10}(?!\d)")
_VIETNAM_TIMEZONE = timezone(timedelta(hours=7), name="Asia/Ho_Chi_Minh")


class _JsonLdParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._capturing = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {name.casefold(): value for name, value in attrs}
        if tag.casefold() == "script" and attributes.get("type", "").casefold() == (
            "application/ld+json"
        ):
            self._capturing = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._capturing:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self._capturing:
            self.blocks.append("".join(self._parts))
            self._capturing = False
            self._parts = []


class _TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


class _JobLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.links.append(href)


class PoliteUrllibTransport:
    """GET-only transport with a fixed minimum interval and no retries/evasion."""

    def __init__(self, minimum_interval_seconds: float = 2.0) -> None:
        self.minimum_interval_seconds = minimum_interval_seconds
        self._last_request_at = 0.0

    def __call__(self, url: str) -> FetchResult:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.minimum_interval_seconds:
            time.sleep(self.minimum_interval_seconds - elapsed)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                result = FetchResult(
                    url=response.geturl(),
                    status=response.status,
                    body=body,
                    fetched_at=datetime.now(UTC),
                    content_type=response.headers.get("Content-Type"),
                )
        except urllib.error.HTTPError as error:
            result = FetchResult(
                url=url,
                status=error.code,
                body=error.read(),
                fetched_at=datetime.now(UTC),
                content_type=error.headers.get("Content-Type"),
            )
        finally:
            self._last_request_at = time.monotonic()
        return result


class PoliteCurlTransport:
    """Optional curl transport for Python runtimes built without an HTTPS backend."""

    def __init__(self, minimum_interval_seconds: float = 2.0) -> None:
        executable = shutil.which("curl.exe") or shutil.which("curl")
        if executable is None:
            raise RuntimeError("curl is not installed")
        self.executable = executable
        self.minimum_interval_seconds = minimum_interval_seconds
        self._last_request_at = 0.0

    def __call__(self, url: str) -> FetchResult:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.minimum_interval_seconds:
            time.sleep(self.minimum_interval_seconds - elapsed)
        marker = b"\n__TOPDEV_PILOT_META__"
        try:
            completed = subprocess.run(
                [
                    self.executable,
                    "--silent",
                    "--show-error",
                    "--location",
                    "--max-redirs",
                    "3",
                    "--max-time",
                    "30",
                    "--user-agent",
                    USER_AGENT,
                    "--write-out",
                    marker.decode() + "%{http_code}\t%{url_effective}\t%{content_type}",
                    url,
                ],
                check=False,
                capture_output=True,
                timeout=40,
            )
        finally:
            self._last_request_at = time.monotonic()
        if marker not in completed.stdout:
            message = completed.stderr.decode("utf-8", errors="replace").strip()
            raise OSError(message or f"curl failed with exit code {completed.returncode}")
        body, metadata = completed.stdout.rsplit(marker, maxsplit=1)
        status_text, effective_url, content_type = metadata.decode("utf-8", errors="replace").split(
            "\t", maxsplit=2
        )
        return FetchResult(
            url=effective_url,
            status=int(status_text),
            body=body,
            fetched_at=datetime.now(UTC),
            content_type=content_type or None,
        )


def extract_job_id(url: str) -> str:
    """Extract the numeric URL suffix; never use JSON-LD ``identifier.value``."""

    matches = _JOB_ID.findall(urlparse(url).path + "/")
    if not matches:
        raise ValueError(f"TopDev URL has no numeric job ID: {url}")
    return matches[-1]


def _is_topdev_job_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc.casefold() not in {"topdev.vn", "www.topdev.vn"}:
        return False
    return bool(_JOB_ID.search(parsed.path + "/")) and (
        "/viec-lam/" in parsed.path or "/detail-jobs/" in parsed.path
    )


def _canonical_job_url(base_url: str, href: str) -> str | None:
    absolute = urljoin(base_url, href)
    parsed = urlparse(absolute)
    canonical = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    return canonical if _is_topdev_job_url(canonical) else None


def _json_ld_objects(html: str) -> tuple[Mapping[str, Any], ...]:
    parser = _JsonLdParser()
    parser.feed(html)
    objects: list[Mapping[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("@type") == "JobPosting":
                objects.append(value)
            graph = value.get("@graph")
            if isinstance(graph, list):
                for item in graph:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for block in parser.blocks:
        try:
            visit(json.loads(block))
        except json.JSONDecodeError:
            continue
    return tuple(objects)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    return rendered or None


def _html_to_text(value: Any) -> str:
    parser = _TextParser()
    parser.feed(str(value or ""))
    text = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    text = _EMAIL.sub("[REDACTED_EMAIL]", text)
    return _PHONE.sub("[REDACTED_PHONE]", text)


def _skills(value: Any) -> tuple[str, ...] | None:
    if isinstance(value, list):
        values = tuple(item for item in (_text(item) for item in value) if item)
        return values
    rendered = _text(value)
    if rendered is None:
        return None
    return tuple(item.strip() for item in re.split(r"[,;|]", rendered) if item.strip())


def _location(value: Any) -> str | None:
    locations = value if isinstance(value, list) else [value]
    parts: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            continue
        address = location.get("address")
        if not isinstance(address, dict):
            continue
        for key in ("streetAddress", "addressLocality", "addressRegion", "addressCountry"):
            if rendered := _text(address.get(key)):
                if rendered not in parts:
                    parts.append(rendered)
    return ", ".join(parts) or None


def _salary(value: Any) -> str | None:
    if not isinstance(value, dict):
        return _text(value)
    salary_value = value.get("value")
    if isinstance(salary_value, dict):
        minimum = _text(salary_value.get("minValue"))
        maximum = _text(salary_value.get("maxValue"))
        if minimum and maximum:
            rendered = f"{minimum}-{maximum}"
        else:
            rendered = minimum or maximum or _text(salary_value.get("value"))
        unit = _text(salary_value.get("unitText"))
    else:
        rendered = _text(salary_value)
        unit = _text(value.get("unitText"))
    if rendered is None:
        return None
    if re.search(r"negotiable|thỏa\s+thuận", rendered, re.I):
        return rendered
    currency = _text(value.get("currency"))
    if currency and currency.casefold() not in rendered.casefold():
        rendered = f"{rendered} {currency}"
    period_alias = {"HOUR": "hour", "MONTH": "month", "YEAR": "year"}
    if unit and (period := period_alias.get(unit.upper())):
        rendered = f"{rendered}/{period}"
    return rendered


def _experience(value: Any) -> str | None:
    if isinstance(value, dict):
        months = value.get("monthsOfExperience")
        if isinstance(months, int | float) and months > 0:
            return f"minimum {months:g} months"
    return _text(value)


def _comparison_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _parse_valid_through(raw_value: str) -> tuple[datetime, bool]:
    stripped = raw_value.strip()
    try:
        parsed_date = date.fromisoformat(stripped)
    except ValueError:
        parsed_date = None
    if parsed_date is not None and len(stripped) == 10:
        return (
            datetime.combine(parsed_date, datetime_time.max, tzinfo=_VIETNAM_TIMEZONE),
            True,
        )
    parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=_VIETNAM_TIMEZONE)
    return parsed, False


def _has_active_application_state(posting: Mapping[str, Any], html: str) -> str | None:
    if match := _ACTIVE_APPLICATION_STATE.search(html):
        return match.group("state")
    potential_action = posting.get("potentialAction")
    actions = potential_action if isinstance(potential_action, list) else [potential_action]
    for action in actions:
        if not isinstance(action, dict):
            continue
        action_type = _text(action.get("@type"))
        action_status = _text(action.get("actionStatus"))
        if action_type == "ApplyAction" or action_status == "PotentialActionStatus":
            return action_status or action_type
    return None


class TopDevAdapter(SourceAdapter):
    """TopDev JSON-LD adapter for the bounded public pilot."""

    def __init__(self, transport: Callable[[str], FetchResult] | None = None) -> None:
        self._transport = transport or PoliteUrllibTransport()
        self._discovery_methods: dict[str, str] = {}

    def discover_job_urls(self, limit: int = 30) -> tuple[str, ...]:
        if not 1 <= limit <= 30:
            raise ValueError("TopDev pilot limit must be between 1 and 30")
        discovered: list[str] = []
        seen_jobs: set[str] = set()
        page_number = 1
        while len(discovered) < limit:
            listing_url = (
                TOPDEV_IT_LISTING if page_number == 1 else f"{TOPDEV_IT_LISTING}?page={page_number}"
            )
            response = self._transport(listing_url)
            if response.status != 200:
                raise RuntimeError(
                    f"IT listing request returned HTTP {response.status}: {listing_url}"
                )
            parser = _JobLinkParser()
            parser.feed(response.body.decode("utf-8", errors="replace"))
            new_jobs = 0
            for href in parser.links:
                location = _canonical_job_url(response.url, href)
                if location is None or location in seen_jobs:
                    continue
                seen_jobs.add(location)
                discovered.append(location)
                self._discovery_methods[location] = f"{DISCOVERY_METHOD}:page={page_number}"
                new_jobs += 1
                if len(discovered) == limit:
                    break
            if new_jobs == 0:
                break
            page_number += 1
        return tuple(discovered)

    def discovery_method_for(self, url: str) -> str:
        """Return listing-page provenance for one discovered canonical URL."""

        return self._discovery_methods.get(url, DISCOVERY_METHOD)

    def fetch_job_detail(self, url: str) -> FetchResult:
        if not _is_topdev_job_url(url):
            raise ValueError(f"Not a supported TopDev job URL: {url}")
        return self._transport(url)

    def detect_closed_state(self, page: FetchResult) -> ClosedStateDecision:
        html = page.body.decode("utf-8", errors="replace")
        comparison = _comparison_timestamp(page.fetched_at)
        if match := _EXPLICIT_JOB_STATE.search(html):
            raw_state = match.group("state").casefold()
            return ClosedStateDecision(
                state="EXPIRED" if raw_state == "expired" else "CLOSED",
                source_field="html:data-job-state",
                raw_value=match.group("state"),
                parsed_datetime=None,
                comparison_timestamp=comparison,
                decision_method="explicit_job_state_marker",
                confidence=1.0,
            )
        objects = _json_ld_objects(html)
        posting = objects[0] if objects else {}
        valid_through = _text(posting.get("validThrough"))
        if valid_through is not None:
            try:
                expiry, is_date_only = _parse_valid_through(valid_through)
            except ValueError:
                expiry = None
            if expiry is not None:
                compared_at = (
                    comparison.astimezone(_VIETNAM_TIMEZONE)
                    if is_date_only
                    else comparison.astimezone(expiry.tzinfo)
                )
                return ClosedStateDecision(
                    state="EXPIRED" if expiry < compared_at else "ACTIVE",
                    source_field="jsonld.validThrough",
                    raw_value=valid_through,
                    parsed_datetime=expiry,
                    comparison_timestamp=compared_at,
                    decision_method="inclusive_valid_through_comparison",
                    confidence=0.98,
                )
        if active_state := _has_active_application_state(posting, html):
            return ClosedStateDecision(
                state="ACTIVE",
                source_field="application_state",
                raw_value=active_state,
                parsed_datetime=None,
                comparison_timestamp=comparison,
                decision_method="explicit_active_application_state",
                confidence=0.95,
            )
        return ClosedStateDecision(
            state="UNKNOWN",
            source_field="jsonld.validThrough",
            raw_value=valid_through,
            parsed_datetime=None,
            comparison_timestamp=comparison,
            decision_method=(
                "malformed_valid_through" if valid_through is not None else "insufficient_evidence"
            ),
            confidence=0.0,
        )

    def extract_raw_record(self, page: FetchResult) -> SourceRawJobRecord:
        if page.status != 200:
            raise ValueError(f"Job page returned HTTP {page.status}: {page.url}")
        html = page.body.decode("utf-8", errors="replace")
        objects = _json_ld_objects(html)
        if not objects:
            raise ValueError(f"No JSON-LD JobPosting found: {page.url}")
        posting = objects[0]
        title = _text(posting.get("title"))
        description = _html_to_text(posting.get("description"))
        if title is None or not description:
            raise ValueError(f"Required title/description missing: {page.url}")
        organization = posting.get("hiringOrganization")
        company = _text(organization.get("name")) if isinstance(organization, dict) else None
        closed_state = self.detect_closed_state(page)
        return SourceRawJobRecord(
            source="topdev",
            source_job_id=extract_job_id(page.url),
            source_url=page.url,
            title_raw=title,
            source_category_raw=_text(posting.get("industry")),
            discovery_method=self.discovery_method_for(page.url),
            company_name_raw=company,
            location_raw=_location(posting.get("jobLocation")),
            salary_raw=_salary(posting.get("baseSalary")),
            skills_raw=_skills(posting.get("skills")),
            posted_at_raw=_text(posting.get("datePosted")),
            expires_at_raw=_text(posting.get("validThrough")),
            experience_raw=_experience(posting.get("experienceRequirements")),
            employment_type_raw=_text(posting.get("employmentType")),
            description_raw=description,
            closed_state=closed_state.state,
            closed_state_provenance=closed_state,
            collected_at=page.fetched_at,
            content_hash=hashlib.sha256(page.body).hexdigest(),
        )

    def normalize_record(self, record: SourceRawJobRecord) -> NormalizedJobRecord:
        return normalize_job_record(
            RawJobRecord(
                source=record.source,
                source_job_id=record.source_job_id,
                source_url=record.source_url,
                title_raw=record.title_raw,
                description_raw=record.description_raw,
                collected_at=record.collected_at,
                salary_raw=record.salary_raw,
                experience_raw=record.experience_raw,
                skills_raw=record.skills_raw,
            )
        )
