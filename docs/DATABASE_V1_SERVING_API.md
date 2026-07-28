# Database V1 Serving and RPC Contract

Migration `20260727_0006` adds a private `serving` schema and an exposed, function-only `api`
schema. It is a read contract over canonical current state, immutable history, and Migration 005
analytics. It does not add a refresh scheduler, frontend, webhook, or application API migration.

## Inventory

The private serving schema contains three tables:

- `serving.refresh_runs` records rebuild, incremental, backfill, validation, and test refreshes.
- `serving.job_search_documents` stores one current, denormalized search document per job posting.
- `serving.job_search_salary_offers` stores the current observation's filterable salary rows.

It also contains seven internal views: `v_current_job_cards`, `v_market_overview_daily`,
`v_company_hiring_daily`, `v_location_demand_daily`, `v_occupation_demand_daily`,
`v_skill_demand_daily`, and `v_salary_metrics_daily`.

The `api` schema contains no tables or views. Its eight versioned `SECURITY DEFINER` functions are
`search_jobs_v1`, `get_job_v1`, `market_overview_v1`, `company_hiring_v1`,
`location_demand_v1`, `occupation_demand_v1`, `skill_demand_v1`, and `salary_metrics_v1`.

## Current-document lineage and search

`serving.build_job_search_document()` locks the canonical `core.job_postings` row, requires a
current observation, and derives the document from that observation and its immutable children.
The document retains posting, observation, source, company, taxonomy, location, salary,
canonical-hash, normalization-version, and refresh lineage. Salary cache rows are validated
against both their history rows and parent document.

The weighted `simple`-configuration search vector ranks normalized title and company most highly,
then occupation and skill labels, followed by location and description. `search_jobs_v1` uses
`websearch_to_tsquery`, deterministic ordering, array filters, status filters, and currency-safe
salary overlap. Search results omit description text; `get_job_v1` returns the current public job
detail.

RPCs read through `v_current_job_cards`, which joins a serving document to the posting's current
observation pointer. A missing or changed pointer immediately hides a stale document even before a
refresh. Concurrent pointer and document updates serialize on the same canonical posting row.

## Security

Row-level security is enabled on all three serving tables. `anon` and `authenticated` receive
usage on `api` and execute only on the eight named functions; they receive no direct serving table
or view privileges. `service_role` receives private serving access for refresh work. Every RPC is
`SECURITY DEFINER`, stable, has a fixed safe search path, and validates bounded parameters before
reading private relations.

## Refresh and downgrade behavior

Serving refreshes are explicitly tracked and may be global or source-scoped. PostgreSQL prevents a
referenced refresh run's source and calculation version from being reassigned. Cache tables are
rebuildable projections; history and analytics remain authoritative.

Downgrade removes the eight exact RPC signatures, internal views, triggers, functions, indexes,
tables, and schemas without `CASCADE`, returning the database to Migration 005.
