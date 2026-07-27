# Database V1 Analytics

Migration `20260727_0005` adds the private `analytics` schema. Its 18 tables form a
warehouse storage contract over immutable Migration 004 history; the migration does not add a
refresh worker, serving view, RPC, API, or dashboard.

## Inventory and grain

The exact inventory is `analytics.refresh_runs`, `analytics.dim_dates`,
`analytics.dim_sources`, `analytics.dim_companies`, `analytics.dim_locations`,
`analytics.dim_occupations`, `analytics.dim_skills`, `analytics.fact_job_observations`,
`analytics.fact_salary_observations`, `analytics.bridge_job_observation_locations`,
`analytics.bridge_job_observation_occupations`, `analytics.bridge_job_observation_skills`,
`analytics.daily_market_metrics`, `analytics.daily_company_hiring`,
`analytics.daily_location_demand`, `analytics.daily_occupation_demand`,
`analytics.daily_skill_demand`, and `analytics.daily_salary_metrics`.

`refresh_runs` records each incremental, backfill, rebuild, validation, or test calculation and
its window, lifecycle, counters, configuration, calculation version, and optional source scope.
`dim_dates` contains every UTC date from 2020-01-01 through 2035-12-31. The source, company,
location, occupation, and skill dimensions retain operational IDs while using stable warehouse
surrogate keys and Type 1 descriptive updates.

`fact_job_observations` has one row per `history.job_observations` row, and
`fact_salary_observations` has one row per `history.observation_salaries` row. Unique history IDs
make repeated fact loads idempotent. The location, occupation, and skill bridges likewise have
one row per matching historical child. Facts and bridges are application-append-only and retain
their producing refresh run. PostgreSQL lineage triggers reject any copied job, source, company,
UTC date, salary, relationship, classification, or dimension identity that disagrees with the
referenced history row. A reusable trigger rejects UPDATE and DELETE on all five fact/bridge
tables with SQLSTATE `23514`; it is not attached to dimensions, refresh runs, or aggregates.

Fact metrics are deterministic: `salary_disclosed` is true iff a disclosed historical salary
exists; child counts count historical skill, occupation, and location rows; first observations have
false status/content change flags, and later flags compare the previous observation's status/hash.
Source-scoped refresh runs must match fact/bridge source lineage; global runs may span sources.

The six mutable daily tables use these complete grains:

- market: UTC date, source, employment type, seniority, and work mode;
- company hiring: UTC date, company, and source;
- location demand: UTC date, location, source, and work mode;
- occupation demand: UTC date, occupation, and source;
- skill demand: UTC date, skill, source, and requirement type;
- salary: UTC date, source, occupation, location, currency, period, and tax basis.

Daily rows are rebuildable. A later refresh implementation must collect all affected dates,
including old dates introduced by late observations, and replace affected grains transactionally.
Every row records `refresh_run_id`, `calculation_version`, and calculation time. Active counts use
the latest observation at the end of the UTC date; event counts use the event's UTC date.

## Counting and unknown values

Counts remain source-posting counts. Advisory duplicate clusters do not automatically reduce
them. Unknown salary remains SQL `NULL`, never zero. Salary aggregates never mix USD with VND,
month with year, or gross with net.

Only `dim_locations` and `dim_occupations` have deterministic analytics-only unknown rows. Both
use surrogate key `-1`; their operational UUID columns are `NULL`, so the warehouse never invents
an operational identity. Other dimension rows map to real operational records.
Occupation and skill rows must match their operational taxonomy version ID, release string, and
parent. Date attributes are derived deterministically from `calendar_date`, and seeded date rows
are immutable. A running refresh must have a start timestamp.

All conformed dimension identities (surrogate and operational) are immutable after assignment;
descriptive Type 1 updates remain allowed, and unknown `-1` rows cannot be converted. Daily rows
must use a source-compatible refresh and exactly its calculation version. Referenced refresh-run
source/version lineage cannot later be changed.

Daily salary checks also preserve range direction: each average or median minimum must be no
greater than its matching maximum when both are present.

## Access and lifecycle

The schema revokes all access from `PUBLIC`. Application/service roles need explicit grants in
deployment configuration. Alembic owns creation, deterministic seeds, constraints, and removal:

```powershell
alembic upgrade head
alembic downgrade 20260727_0004
alembic upgrade head
```

The downgrade removes only `analytics`; Migrations 001–004 remain. Migration 006 is reserved for
a separately reviewed serving layer. It may define stable read contracts, but it must not be
assumed to exist from this storage migration.
