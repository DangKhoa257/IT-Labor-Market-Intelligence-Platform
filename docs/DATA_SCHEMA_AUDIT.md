# Canonical Schema Audit — Phase 1A

**Status:** audit only. `DATA_SCHEMA.md`, the gold CSV header and database model are not changed by this document.

## Purpose

Compare the Gemini recommendations with Phase 0 null/provenance rules and the bounded source-verification evidence. Recommendations below are proposed changes or explicit rejections; they require a separate schema decision.

## Recommendations to reject or change

| Gemini assumption/recommendation | Decision | Required treatment |
|---|---|---|
| Missing work mode defaults to Onsite | Reject | `work_mode=null`/UNSPECIFIED unless direct text or a documented inference rule supports onsite, hybrid or remote. |
| Salary currency defaults to VND when salary is undisclosed | Reject | Keep `salary_currency=null` when no numeric salary/currency evidence exists. A source JSON-LD currency beside `Negotiable` must be retained as source evidence but not automatically accepted canonically. |
| Salary type defaults to Gross | Reject | Keep `salary_type=null`/UNSPECIFIED unless gross, net, negotiable or another type is stated or deterministically parsed. |
| Null experience means zero years | Reject | Null means missing/unknown. Zero is allowed only for explicit “no experience required” evidence. |
| Hidden company and unknown company are equivalent | Reject | Add a visibility/status concept such as `company_name_status = disclosed | hidden_by_source | absent | parse_error`, or equivalent field-level metadata. |
| Record-level provenance is sufficient | Change | Direct, normalized and inferred values need field-level provenance: evidence location/type, source value and transformation/rule version. |
| One aggregate confidence score is sufficient | Change | Every inferred value needs an inference method/rule ID and field-level confidence. Aggregate confidence may remain only as a summary. |
| One job category is always sufficient | Change | Evaluate `primary_job_category` plus zero-or-more `secondary_job_categories`, especially for hybrid/multi-role postings. Keep the current field until gold annotation validates the change. |
| JSON-LD `identifier` is the job ID | Reject as a general rule | In three TopDev samples it represented a company identifier, while the job ID was the numeric URL suffix. Define and test an ID rule per source; retain the evidence method. |
| A structured field is automatically canonical-quality | Reject | Preserve direct source values, then validate semantics. TopDev returned `employmentType=OTHER` for all three samples and encoded numeric salary ranges as strings. |
| Sitemap disappearance proves a job is inactive | Reject | A missing sitemap entry is an observation signal only. `is_active=false` requires a versioned lifecycle policy and corroborating expiry/closed response evidence. |
| Relative or refreshed date is always the original posting date | Reject | Preserve source date semantics and precision. Do not equate observed/updated/refreshed dates with `posted_at` without explicit evidence. |
| One scalar city covers every posting | Change | Evaluate a repeatable `locations` structure; do not collapse multi-city, remote or nationwide postings into one inferred city. |
| Salary “Negotiable” still has a disclosed numeric salary | Reject | `salary_disclosed=false`, numeric bounds null. Currency/period remain null canonically unless explicitly meaningful despite nondisclosure. |
| Description-derived values are direct fields | Reject | Mark them `DESCRIPTION_DERIVED`, store evidence span/section and apply normalization/inference metadata as appropriate. |
| First 200 description characters plus title/company is a safe duplicate identity | Reject as authoritative identity | Such a hash may be a candidate signal, never a destructive merge key. Preserve source postings and provenance; benchmark pair/cluster decisions. |
| Raw descriptions can be retained indefinitely by default | Reject | Retention, access and redaction must be approved per source. Store only what is necessary and permitted. |
| Missing values can be filled from platform conventions | Reject | Platform conventions are not posting evidence. Missing values remain null unless a documented, benchmarked inference explicitly applies. |

## Proposed provenance model for later design

For each canonical field, evaluate a companion evidence record rather than adding dozens of flat columns:

- canonical field name;
- classification: `DIRECT_STRUCTURED`, `DIRECT_HTML`, `DESCRIPTION_DERIVED`, `INFERRED`, `NOT_AVAILABLE` or `UNVERIFIED`;
- raw source value or safe evidence reference;
- evidence path/selector/JSON pointer;
- extraction method and extractor version;
- normalization rule version;
- inference method and confidence when applicable;
- reviewed/overridden status.

This is a design direction, not an implemented entity or migration.

## Evidence from the Phase 1A sample

- TopDev URL suffixes supplied job IDs; JSON-LD identifiers supplied different values associated with companies.
- TopDev `JobPosting` JSON-LD exposed title, organization, location, dates, skills, experience and salary evidence.
- TopDev salary ranges were strings; one nondisclosed salary still carried VND/month metadata.
- TopDev employment type was only `OTHER` in the three active samples.
- TopDev work mode, seniority and company size were not established by the retained structured evidence.
- No ITviec or Glints detail data was sampled because policy gates required a stop.

## Decision gate

Do not update `DATA_SCHEMA.md` until:

1. at least one source is approved for continued verification;
2. additional bounded samples validate the proposed distinctions;
3. schema versioning and migration impact are reviewed;
4. gold annotation guidelines and template changes are prepared together;
5. automated schema-consistency tests are updated in the same change.
