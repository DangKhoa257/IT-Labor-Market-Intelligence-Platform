# Database V1 Serving and RPC Contract

Migration `20260727_0006` adds a private `serving` schema and an exposed, function-only `api`
schema. It is a read contract over canonical current state, immutable history, and Migration 005
analytics. It does not add a refresh scheduler, frontend, webhook, or application API migration.

Migration 007 preserves all eight API contracts and exact API grants. It adds private operations
evidence and security hardening without exposing an operations endpoint or relation.

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
against both their history rows and parent document. An AFTER document trigger atomically replaces
the salary projection from immutable history, so loaders never copy or mutate serving salaries.
Both the document builder and refresh-lineage mutation lock the same refresh-run row; salary
validation and rebuilding likewise lock the parent document.

Creating a serving document also finalizes its observation snapshot against later description,
location, salary, skill, and occupation inserts. The builder and child triggers share the parent
history-observation lock, making child-first and document-first transactions deterministic. Event
tables remain unaffected.

The weighted `simple`-configuration search vector ranks normalized title and company most highly,
then occupation and skill labels, followed by location and description. `search_jobs_v1` uses
`websearch_to_tsquery`, deterministic ordering, array filters, status filters, and currency-safe
salary overlap. Public inputs reject NULL pagination/sort values, queries over 500 characters, and
filter arrays with NULL elements or over 100 members. Relevance ties use posted time and posting ID;
blank relevance searches use newest posting time and posting ID. Search results omit description
text; `get_job_v1` returns the current public job detail.

Valid description redaction or expiry immediately deletes the matching serving document in the
same transaction, so neither RPCs nor full-text search retain the excerpt. Salary cache rows
cascade-delete, history remains unchanged, and a later rebuild contains no redacted text.

RPCs read through `v_current_job_cards`, which joins a serving document to the posting's current
observation pointer. A missing or changed pointer immediately hides a stale document even before a
refresh. Concurrent pointer and document updates serialize on the same canonical posting row.

## Security

Row-level security is enabled on all three serving tables. `anon` and `authenticated` receive
usage on `api` and execute only on the eight named functions; they receive no direct serving table
or view privileges. `service_role` can maintain refresh runs and documents and can only select the
database-maintained salary projection. Every RPC is
`SECURITY DEFINER`, stable, has a fixed safe search path, and validates bounded parameters before
reading private relations.

Dashboard functions expose stable explicit table returns with source/company, location,
occupation, skill, and salary descriptors. Unknown location/occupation inclusion defaults to
false, and no API return type depends on a private serving view composite type. Location and skill
pagination order by their complete public grains. Job detail includes `salary_disclosed`
immediately before salary offers.

## Refresh and downgrade behavior

Serving refreshes are explicitly tracked and may be global or source-scoped. PostgreSQL prevents a
referenced refresh run's source and calculation version from being reassigned. Cache tables are
rebuildable projections; history and analytics remain authoritative.

Downgrade removes the eight exact RPC signatures, internal views, triggers, functions, indexes,
tables, and schemas without `CASCADE`, returning the database to Migration 005. Cross-schema
history triggers are removed before their serving functions and schema.
