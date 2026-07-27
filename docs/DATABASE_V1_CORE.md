# Database V1 Core and Taxonomy

Migration `20260726_0003` adds the private `taxonomy` and `core` schemas. It is a
current-state storage layer, not a history, analytics, serving, API, or import-service release.

It creates exactly these tables:

- `taxonomy.taxonomy_versions`, `taxonomy.employment_types`,
  `taxonomy.seniority_levels`, `taxonomy.occupations`, `taxonomy.occupation_aliases`,
  `taxonomy.skills`, and `taxonomy.skill_aliases`;
- `core.locations`, `core.companies`, `core.company_aliases`, `core.company_domains`,
  `core.job_postings`, `core.job_posting_descriptions`, `core.job_posting_locations`,
  `core.salary_offers`, `core.job_posting_skills`, and `core.job_posting_occupations`.

## Source posting identity

`core.job_postings` represents one posting from one source. Its stable identity is
`(source_id, source_job_id)`. The same source job ID may exist at another source and remains a
separate posting. A composite foreign key permits `latest_extracted_record_id` only when the
extracted record has the posting's own `(source_id, source_job_id)` identity. Deleting that
extraction sets only `latest_extracted_record_id` to null; the posting's source identity is
preserved.

The current Phase 3 API continues to use the unqualified prototype ORM tables. It does not read
Migration 003 tables. A later, focused application service will map accepted
`ingestion.extracted_records` into this layer.

## Companies and aliases

Company normalized names are indexed but deliberately not unique. Two real organizations may
share a normalized name, and a name match alone is insufficient evidence for a merge. Candidate
companies retain source/global aliases and domains independently. A company referenced by a job
cannot be deleted; merges and retirement require a later audited workflow.

## Locations

Locations are canonical entities keyed by `resolution_key`. A posting has repeatable
`job_posting_locations` rows, so multiple workplaces and applicant-eligibility scopes are not
collapsed into one city. A partial unique index permits only one primary location for each
posting/relationship type. Remote assignments require an explicit remote scope, and non-remote
assignments require the scope to be null.

## Salary disclosure

Salary data lives in `core.salary_offers`, not on `job_postings`. Multiple components and periods
remain separate rows, preventing monthly, annual, currency, tax-basis, or component values from
being mixed. A disclosed salary requires at least one numeric source amount. A nondisclosed,
negotiable salary must have null source numeric amounts. Estimated values are explicitly marked;
normalization ranges and optional FX rate/date pairs are validated independently.

## Versioned taxonomy

Occupation and skill releases are registered in `taxonomy.taxonomy_versions`. Canonical codes are
unique only within a taxonomy version. Aliases may repeat across different skills or occupations,
while duplicates for the same entity and source scope are rejected. Employment types and
seniority levels are deterministic reference rows seeded by the migration. A taxonomy version's
`taxonomy_type` is immutable after insertion, while other fields may be updated when valid.

PostgreSQL triggers require occupations to use occupation taxonomy versions and skills to use
skill taxonomy versions. Composite self-references require every parent to belong to the same
taxonomy version as its child.

`job_posting_skills` preserves requirement type (`required`, `preferred`, `mentioned`, or
`unknown`). `job_posting_occupations` supports one primary and multiple secondary occupations.

## Current state versus history

Migration 003 stores current posting state and one currently retained description. Migration 004
adds immutable observations, complete child snapshots, and status/change/repost events in
`history`; `current_observation_id` points only to an observation for the same posting. An
unchanged recrawl updates `last_seen_at` without requiring a new observation, and repeated hashes
such as A → B → A remain valid distinct history. Fetch failures still do not imply posting closure.

Quality review and advisory duplicate groups live in the Migration 004 `quality` schema. They do
not merge or delete source postings. See
[DATABASE_V1_HISTORY_QUALITY.md](DATABASE_V1_HISTORY_QUALITY.md).

Alembic migration revisions and extractor versions are independent version systems. Gold examples
use a generic synthetic extractor version and do not encode `m003` merely because their storage
contract is documented alongside Migration 003.

## Security and migration operations

`core` and `taxonomy` revoke schema privileges from PostgreSQL `PUBLIC`. No grants are made to
Supabase `anon` or `authenticated`, and no RLS/API surface is introduced.

```powershell
alembic upgrade head
alembic current
alembic downgrade 20260726_0002
alembic upgrade head
```

Downgrading to 002 removes only Migration 003 tables and the `core`/`taxonomy` schemas. The
`system` and `ingestion` schemas remain intact. Because no full canonical importer exists yet,
operators must not point the legacy Phase 3 importer at these tables.
