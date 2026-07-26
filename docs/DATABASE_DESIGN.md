# Database Design

PostgreSQL 16 is the production database. Database V1 migrations 001 and 002 currently provide
the private `system` and `ingestion` schemas and the evidence lineage from source configuration
through direct extraction. See [DATABASE_V1_FOUNDATION.md](DATABASE_V1_FOUNDATION.md) for the
table map, identity strategy, storage rules, security boundary, and baseline-reset decision.

The existing unqualified Phase 3 ORM (`Source`, canonical job, company, skill, snapshot, quality,
and duplicate models) remains a prototype used by the current read-only API and isolated SQLite
tests. It is not the Database V1 migration contract and is not created by the V1 Alembic chain.
Later reviewed migrations must introduce canonical tables without conflating them with ingestion
evidence.

Configuration comes from `DATABASE_URL`. PostgreSQL-specific migration behavior is tested on
PostgreSQL; SQLite remains restricted to isolated prototype unit tests.

```powershell
alembic upgrade head
alembic current
alembic downgrade 20260726_0001
```

No V1 migration uses metadata-driven `create_all()`/`drop_all()`, native enums, generic JSON, or
destructive `CASCADE` DDL.
