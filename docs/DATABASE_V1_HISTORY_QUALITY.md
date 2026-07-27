# Database V1 History and Data Quality

Migration `20260727_0004` adds the private `history` and `quality` schemas. It records immutable
canonical observations, lifecycle/change/repost events, field evidence, mutable quality-review
issues, and advisory duplicate groups. It does not implement the writer, diff engine, scheduler,
deduplication algorithm, analytics warehouse, API, or dashboard.

It creates exactly these tables:

- `history.job_observations`, `history.observation_descriptions`,
  `history.observation_locations`, `history.observation_salaries`,
  `history.observation_skills`, `history.observation_occupations`,
  `history.job_status_events`, `history.job_change_events`, and `history.job_repost_events`;
- `quality.validation_runs`, `quality.data_quality_issues`, `quality.field_evidence`,
  `quality.duplicate_candidates`, `quality.duplicate_clusters`, and
  `quality.duplicate_cluster_members`.

## Current state and observations

`core.job_postings` remains the current source-scoped state. Its nullable
`current_observation_id` may reference only an observation belonging to that same posting.
`history.job_observations` also proves that the posting and extracted record have the same
`(source_id, source_job_id)` identity. An unchanged successful recrawl updates
`core.job_postings.last_seen_at` without requiring another observation.

Observation crawl lineage is source-consistent and restrictive: a non-null crawl run must belong
to the observation's source, and a referenced crawl run cannot be deleted. Historical salary
snapshots are self-contained and intentionally have no foreign key to mutable current
`core.salary_offers` rows, so replacing or deleting current salary state cannot rewrite or block
the historical snapshot.

Observations are versioned by extracted record and normalization version, not by canonical hash.
Therefore a posting may move from hash A to B and later back to A while retaining distinct,
ordered lineage. Description, location, salary, skill, and occupation tables store complete child
snapshots for an observation.

## Lifecycle and change events

Statuses are `active`, `expired`, `closed`, `removed`, and `unknown`. Status events record explicit
transitions and may identify first-seen, source state, elapsed expiry, repeated-not-found,
reactivation, manual correction, or backfill evidence. One failed fetch never establishes closure
or removal. Change events record field-level before/after values between two observations of the
same job. Repost events are also constrained to observations of one job.

The migration creates storage only. It does not automatically compare observations, infer
lifecycle transitions, schedule checks, or write these rows.

## Append-only records

PostgreSQL triggers reject updates and deletes for observations, immutable historical child
snapshots, history events, and duplicate candidates with SQLSTATE `23514`. A specialized
description trigger permits only one retention action: remove non-null text while moving to
`redacted` or `expired`; it rejects deletion, restoration, and all other changes.

Field evidence content and lineage remain immutable, but a specialized trigger permits updates to
its review status, reviewer, review time, and notes. Verified/rejected evidence requires reviewer
identity and time and cannot return to `unreviewed`. Field evidence classifications are `direct_structured`, `direct_html`,
`description_derived`, `normalized`, `inferred`, `not_available`, and `unverified`. Normalized
evidence requires its rule and version; inferred evidence requires its method; unavailable fields
must not claim raw or normalized values.

## Quality review and duplicate groups

Validation runs track scope, rule version, lifecycle, counters, and object-shaped metrics. Quality
issues move through `open`, `acknowledged`, `resolved`, `false_positive`, or `suppressed`; resolved
states require a resolution timestamp, and review timestamps require a reviewer.

Source-only issues are valid. When additional context is stated, composite PostgreSQL foreign keys
prove crawl runs, extracted records, jobs, and observations belong to the stated source/job.
Quality-issue context uses restrictive deletion, so evidence lineage cannot silently disappear.

Duplicate candidates and clusters are advisory. Canonical candidate pairs have a stable UUID
ordering, and a cluster has at most one representative. Removing a cluster deletes only its
membership rows. It never deletes, merges, or rewrites source postings.

## Operations and downgrade

```powershell
alembic upgrade head
alembic current
alembic downgrade 20260726_0003
alembic upgrade head
```

Downgrading to Migration 003 removes only Migration 004 tables, schemas, triggers, the current
observation pointer, and its supporting core identity constraint. Migrations 001–003, including
the extracted-record source-identity constraint, remain intact. The next planned database layer is
the separately reviewed analytics warehouse migration.
