# Database Design

PostgreSQL 16 is the production database. Database V1 migrations 001 and 002 provide private
`system` and `ingestion` schemas and evidence lineage. Migration 003 adds private, versioned
`taxonomy` reference data and the canonical current-state `core` schema. Migration 004 adds
immutable `history` and review-oriented `quality` storage. See
[DATABASE_V1_FOUNDATION.md](DATABASE_V1_FOUNDATION.md) and
[DATABASE_V1_CORE.md](DATABASE_V1_CORE.md), plus
[DATABASE_V1_HISTORY_QUALITY.md](DATABASE_V1_HISTORY_QUALITY.md).

The existing unqualified Phase 3 ORM (`Source`, canonical job, company, skill, snapshot, quality,
and duplicate models) remains a prototype used by the current read-only API and isolated SQLite
tests. It is not the Database V1 migration contract and is not created by the V1 Alembic chain.
The API remains compatible by continuing to use those prototype tables. Migrations 003 and 004 do
not rewrite API repositories, and no full canonical importer, observation writer, automatic diff,
lifecycle scheduler, or deduplication algorithm is included.

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

```powershell
alembic upgrade head
alembic current
alembic downgrade 20260726_0003
```

No V1 migration uses metadata-driven `create_all()`/`drop_all()`, native enums, generic JSON, or
destructive `CASCADE` DDL.
