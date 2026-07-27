# Database Design

PostgreSQL 16 is the production database. Database V1 migrations 001 and 002 provide private
`system` and `ingestion` schemas and evidence lineage. Migration 003 adds private, versioned
`taxonomy` reference data and the canonical current-state `core` schema. See
[DATABASE_V1_FOUNDATION.md](DATABASE_V1_FOUNDATION.md) and
[DATABASE_V1_CORE.md](DATABASE_V1_CORE.md).

The existing unqualified Phase 3 ORM (`Source`, canonical job, company, skill, snapshot, quality,
and duplicate models) remains a prototype used by the current read-only API and isolated SQLite
tests. It is not the Database V1 migration contract and is not created by the V1 Alembic chain.
The API remains compatible by continuing to use those prototype tables. Migration 003 does not
rewrite API repositories and no full canonical importer is included.

Configuration comes from `DATABASE_URL`. PostgreSQL-specific migration behavior is tested on
PostgreSQL; SQLite remains restricted to isolated prototype unit tests.

Database V1 enforces source-scoped extracted-record lineage, taxonomy-version type and parent
integrity, and bidirectional remote-scope consistency in PostgreSQL rather than relying on importer
behavior. Alembic revision identifiers and extractor build versions remain independent.

```powershell
alembic upgrade head
alembic current
alembic downgrade 20260726_0002
```

No V1 migration uses metadata-driven `create_all()`/`drop_all()`, native enums, generic JSON, or
destructive `CASCADE` DDL.
