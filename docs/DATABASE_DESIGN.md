# Database Design

PostgreSQL 16 is the production database. Database V1 migrations 001 and 002 provide private
`system` and `ingestion` schemas and evidence lineage. Migration 003 adds private, versioned
`taxonomy` reference data and the canonical current-state `core` schema. Migration 004 adds
immutable `history` and review-oriented `quality` storage. Migration 005 adds the private,
observation-derived `analytics` warehouse and rebuildable daily aggregates. See
[DATABASE_V1_FOUNDATION.md](DATABASE_V1_FOUNDATION.md) and
[DATABASE_V1_CORE.md](DATABASE_V1_CORE.md), plus
[DATABASE_V1_HISTORY_QUALITY.md](DATABASE_V1_HISTORY_QUALITY.md), plus
[DATABASE_V1_ANALYTICS.md](DATABASE_V1_ANALYTICS.md).

The existing unqualified Phase 3 ORM (`Source`, canonical job, company, skill, snapshot, quality,
and duplicate models) remains a prototype used by the current read-only API and isolated SQLite
tests. It is not the Database V1 migration contract and is not created by the V1 Alembic chain.
The API remains compatible by continuing to use those prototype tables. Migrations 003–005 do not
rewrite API repositories, and no full canonical importer, observation writer, automatic diff,
lifecycle scheduler, analytics scheduler, serving layer, or deduplication algorithm is included.

Configuration comes from `DATABASE_URL`. PostgreSQL-specific migration behavior is tested on
PostgreSQL; SQLite remains restricted to isolated prototype unit tests.

Database V1 enforces source-scoped extracted-record lineage, immutable taxonomy-version types,
taxonomy parent integrity, and bidirectional remote-scope consistency in PostgreSQL rather than
relying on importer behavior. Alembic revision identifiers and extractor build versions remain
independent.

Migration 004 avoids foreign-key actions that would mutate append-only history. Historical salary
snapshots are independent of current salary rows, crawl lineage is restrictive, and specialized
triggers expose only one-way description retention and field-evidence review transitions. Quality
context is source-consistent and deletion-restricted.

Migration 005 facts map uniquely to immutable history rows. Daily aggregates are mutable so late
data can rebuild old UTC dates. Their full grains preserve source, work mode, skill requirement,
and salary currency/period/tax basis. Analytics-only `-1` location and occupation members have no
invented operational UUID. Duplicate clusters remain advisory and do not reduce posting counts.
PostgreSQL validates copied fact and bridge lineage against immutable history and makes those five
tables append-only. Taxonomy dimension identities, deterministic immutable dates, refresh-run
lifecycle, and salary aggregate range directions are enforced in Migration 005 DDL. Conformed
dimension identities and referenced refresh-run source/calculation lineage are immutable, while
descriptive Type 1 updates remain allowed.

```powershell
alembic upgrade head
alembic current
alembic downgrade 20260727_0004
```

No V1 migration uses metadata-driven `create_all()`/`drop_all()`, native enums, generic JSON, or
destructive `CASCADE` DDL.
