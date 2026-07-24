# TopDev Pilot Adapter

## Scope

`TopDevAdapter` is the first bounded source adapter. It reads public sitemap and job-detail responses,
extracts JSON-LD `JobPosting` evidence, and sends the extracted record through the existing
source-independent normalization pipeline. The adapter version is `topdev.v1`.

This is a low-volume pilot implementation, not a scheduler or general crawler. It enforces a maximum
discovery limit of 30, uses GET requests with a descriptive user agent, waits at least two seconds
between live requests, has no login behavior, and does not retry or work around CAPTCHA, HTTP 403, or
anti-bot responses.

## Interface

All adapters implement `SourceAdapter`:

- `discover_job_urls(limit)` returns unique public detail URLs in deterministic discovery order.
- `fetch_job_detail(url)` fetches one validated source URL.
- `extract_raw_record(page)` returns `SourceRawJobRecord`.
- `normalize_record(record)` delegates to `normalize_job_record`.
- `detect_closed_state(page)` returns `active`, `expired`, or `unknown` from explicit evidence.

The transport is injectable. Tests use in-memory responses; the default transport uses Python's
standard library. A curl transport is available for Python runtimes built without HTTPS support; it
uses the same identity, timeout, redirect cap, rate interval, and no-retry behavior.

## Discovery

Discovery starts at the source-labeled IT listing `https://topdev.vn/viec-lam/tim-kiem` and follows
its existing numbered pages with `?page=N` until the requested limit is reached. It accepts only
HTTPS `topdev.vn`/`www.topdev.vn` paths containing `/viec-lam/` or `/detail-jobs/` plus a numeric
suffix. Query/fragment tracking values are removed and duplicate URLs are discarded before fetching.

The global job sitemap is not used for the IT pilot. Audit evidence showed that its newest entries
mixed IT jobs with banking, sales, marketing, retail, and legal roles. JSON-LD `industry` also emitted
`Information Technology` for those non-IT pages, so that value is accepted only together with
curated IT-listing discovery provenance. It is not a standalone scope signal.

## Extraction rules

The source job ID always comes from the numeric URL suffix. JSON-LD `identifier.value` is never used
as the job ID because verified samples show it may identify the company.

The adapter extracts title, hiring organization, location address components, base salary, skills,
posted/expiry dates, experience requirements, raw employment type, description, closed state,
collection time, and a SHA-256 response hash. HTML descriptions are converted to plain text. Email
addresses and phone-like contact strings are redacted before the record is retained.

Scope classification requires curated IT-listing provenance. Because that listing can still contain
adjacent/non-IT roles, the classifier then checks source tags: explicit technical tags admit a record,
while unopposed banking, sales, marketing, HR, accounting, legal, CAD/construction, or social-media
tags reject it. Canonical category/skill evidence and a bounded set of IT-role titles are fallbacks
only when corroborated by listing provenance and the source category. A title match alone cannot
admit a URL from another discovery surface. Title normalization remains output diagnostics rather
than the sole source-scope gate.

Important conservative behavior:

- `employmentType=OTHER` remains raw evidence and is not mapped to a canonical employment type.
- Negotiable salary retains only the negotiable phrase; misleading currency/period metadata does not
  create numeric salary or currency values.
- Numeric salary metadata is combined only when explicitly present in JSON-LD.
- `monthsOfExperience` is rendered as an explicit minimum-month phrase and normalized to decimal
  years. A zero value does not become zero years; only an explicit no-experience phrase can do that.
- Missing location, salary, skills, experience, and employment type remain null.
- No work mode is created when `jobLocationType` or equivalent explicit evidence is absent.
- Required title/description or missing JSON-LD `JobPosting` rejects the record.
- An expired marker or a past `validThrough` can mark a page expired even when HTTP status is 200.

## Output

Each line of `datasets/processed/topdev_pilot.jsonl` contains two objects:

- `raw`: direct or minimally rendered source evidence from `SourceRawJobRecord`;
- `normalized`: salary, experience, skills, title/category, provenance, and validation results from
  the offline processing foundation.

Raw response pages are not written to disk by the pilot. The processed JSONL is internal pilot data
and is ignored by Git according to the repository dataset rules.
