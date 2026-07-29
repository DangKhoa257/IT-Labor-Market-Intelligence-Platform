# Read-Only API Reference

Migration 007 adds no public RPC functions. `operations` is private and service-role-only; the
eight Version 1 API functions and their public contracts remain unchanged.

Start the application with `uvicorn apps.api.main:app --reload`. Swagger is available at `http://127.0.0.1:8000/docs` and OpenAPI JSON at `/openapi.json`.

The API exposes `/health` and the following `/api/v1` resources:

- `GET /jobs` and `GET /jobs/{job_id}`
- `GET /companies` and `GET /companies/{company_id}`
- `GET /skills`
- `GET /analytics/overview`
- `GET /analytics/categories`
- `GET /analytics/skills`
- `GET /analytics/salaries`
- `GET /analytics/locations`
- `GET /quality/summary`
- `GET /duplicates`

Jobs support pagination, keyword search, category, city, company, skill, employment type, work mode, status, disclosed salary, salary-range filters, and deterministic sorting by posted date, collected date, or salary. List responses omit descriptions. Detail responses provide at most a 500-character HTML-stripped preview.

Analytics are descriptive for the persisted sample. Currency groups are never combined.

Salary responses identify `posting_range_midpoint` as the observation basis. When a currency has `sample_count=1`, `statistically_meaningful` is false and the returned mean/median must be read only as that posting's range midpoint.

Quality summaries separate accepted and rejected records, INFO-only notices, WARNING/ERROR records, and deterministic title-classification coverage. INFO notices such as `title_unclassified` do not make a record rejected. Duplicate responses include source identities and URLs for every advisory cluster member.

## Database V1 function-only RPC contract

Migration 006 separately exposes eight PostgreSQL RPC functions in `api`: `search_jobs_v1`,
`get_job_v1`, `market_overview_v1`, `company_hiring_v1`, `location_demand_v1`,
`occupation_demand_v1`, `skill_demand_v1`, and `salary_metrics_v1`. The schema contains functions
only. `anon` and `authenticated` can execute exactly those functions but cannot read private
`serving` tables or views directly. Search and detail RPCs hide serving documents whose
observation no longer matches the canonical current-observation pointer.

Search rejects NULL pagination/sort values, queries longer than 500 characters, NULL-bearing or
oversized filter arrays, and invalid salary bounds. Relevance and date sorts have stable posted-time
and posting-ID tie breakers. Dashboard RPCs expose explicit descriptive columns; location,
occupation, and salary unknown-dimension flags default to false. Serving salary rows are generated
atomically from the selected immutable observation rather than accepted as loader-provided copies.

Creating a serving document finalizes its five historical child collections against later inserts
with transaction-safe observation locking. Description redaction or expiry invalidates the serving
document immediately; the job can temporarily disappear until rebuilt without the excerpt or its
search terms. `get_job_v1` reports `salary_disclosed` immediately before `salary_offers_json`.
Location and skill dashboard pagination use their complete grains, preventing page-boundary gaps
or duplicates.
