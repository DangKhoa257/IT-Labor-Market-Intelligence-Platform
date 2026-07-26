"""PostgreSQL 16 integration tests for Database V1 migrations 001 and 002."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import cast
from uuid import UUID

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from it_labor_market_intelligence.database.v1_models import Source

DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="Database V1 integration tests require PostgreSQL",
)

FOUNDATION_TABLES = {
    "system": {"pipeline_versions", "retention_policies", "background_jobs", "audit_events"},
    "ingestion": {
        "sources",
        "source_policies",
        "parser_versions",
        "crawl_runs",
        "crawl_tasks",
        "raw_objects",
        "fetch_events",
        "extraction_runs",
        "extracted_records",
        "crawl_errors",
    },
}


@pytest.fixture(scope="module")
def engine() -> Iterator[sa.Engine]:
    migration_config = Config("alembic.ini")
    migration_config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.upgrade(migration_config, "head")
    value = sa.create_engine(DATABASE_URL)
    yield value
    value.dispose()


def _source(connection: sa.Connection, slug: str = "example") -> UUID:
    return cast(
        UUID,
        connection.execute(
            sa.text(
                """
            INSERT INTO ingestion.sources (slug, display_name, base_url, status, is_enabled)
            VALUES (:slug, 'Example Source', 'https://example.test', 'approved', true)
            RETURNING id
        """
            ),
            {"slug": slug},
        ).scalar_one(),
    )


def _reject(engine: sa.Engine, statement: str, parameters: dict[str, object]) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(sa.text(statement), parameters)


def test_empty_database_schema_inventory_and_current_revision(engine: sa.Engine) -> None:
    inspector = sa.inspect(engine)
    assert set(inspector.get_schema_names()) >= {"system", "ingestion"}
    for schema, tables in FOUNDATION_TABLES.items():
        assert set(inspector.get_table_names(schema=schema)) == tables
    with engine.connect() as connection:
        assert connection.scalar(
            sa.text("SELECT extname FROM pg_extension WHERE extname='pgcrypto'")
        )
        assert (
            connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == "20260726_0002"
        )


def test_model_uuid_default_and_jsonb_round_trip(engine: sa.Engine) -> None:
    with Session(engine) as session:
        source = Source(
            slug="orm-source",
            display_name="ORM Source",
            base_url="https://orm.example.test",
            status="approved",
            metadata_json={"fixture": "SYNTHETIC_TEST_DATA"},
        )
        session.add(source)
        session.commit()
        session.refresh(source)
        assert isinstance(source.id, UUID)
        assert source.metadata_json == {"fixture": "SYNTHETIC_TEST_DATA"}


@pytest.mark.parametrize(
    ("statement", "parameters"),
    [
        (
            "INSERT INTO ingestion.sources (slug, display_name, base_url, status, is_enabled) "
            "VALUES ('Invalid Slug', 'Bad', 'https://example.test', 'approved', false)",
            {},
        ),
        (
            "INSERT INTO ingestion.sources (slug, display_name, base_url, status, is_enabled) "
            "VALUES ('not-approved', 'Bad', 'https://example.test', 'researching', true)",
            {},
        ),
    ],
)
def test_source_constraints(
    engine: sa.Engine, statement: str, parameters: dict[str, object]
) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(sa.text(statement), parameters)


def test_policy_json_arrays_and_raw_object_storage_constraints(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        source_id = _source(connection, "constraint-source")
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion.source_policies
                    (source_id, policy_version, approved_paths, blocked_paths)
                VALUES (:source_id, 'bad-json', '{}'::jsonb, '[]'::jsonb)
            """
            ),
            {"source_id": source_id},
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                """
            INSERT INTO ingestion.raw_objects (sha256, storage_provider, byte_size)
            VALUES (:sha, 'inline', 1)
        """
            ),
            {"sha": "a" * 64},
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                """
            INSERT INTO ingestion.raw_objects (sha256, storage_provider, byte_size)
            VALUES (:sha, 'filesystem', 1)
        """
            ),
            {"sha": "b" * 64},
        )


def test_run_task_raw_and_timestamp_constraints(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        source_id = _source(connection, "checklist-source")
        run_id = connection.execute(
            sa.text(
                """
                INSERT INTO ingestion.crawl_runs (source_id, run_type, trigger_type)
                VALUES (:source_id, 'test', 'test') RETURNING id
            """
            ),
            {"source_id": source_id},
        ).scalar_one()
        connection.execute(
            sa.text(
                """
                INSERT INTO ingestion.raw_objects
                    (sha256, storage_provider, inline_payload_json, byte_size)
                VALUES (:sha, 'inline', '{}'::jsonb, 2)
            """
            ),
            {"sha": "d" * 64},
        )

    _reject(
        engine,
        """INSERT INTO ingestion.sources (slug, display_name, base_url)
           VALUES ('checklist-source', 'Duplicate', 'https://example.test')""",
        {},
    )
    for values in (
        {"requested_limit": 0, "status": "pending", "discovered_count": 0},
        {"requested_limit": 1, "status": "unknown", "discovered_count": 0},
        {"requested_limit": 1, "status": "pending", "discovered_count": -1},
    ):
        _reject(
            engine,
            """
                INSERT INTO ingestion.crawl_runs
                    (source_id, run_type, trigger_type, requested_limit, status, discovered_count)
                VALUES (:source_id, 'test', 'test', :requested_limit, :status, :discovered_count)
            """,
            {"source_id": source_id, **values},
        )
    _reject(
        engine,
        """
            INSERT INTO ingestion.crawl_tasks (crawl_run_id, source_id, task_type)
            VALUES (:run_id, :source_id, 'detail_page')
        """,
        {"run_id": run_id, "source_id": source_id},
    )
    _reject(
        engine,
        """
            INSERT INTO ingestion.raw_objects
                (sha256, storage_provider, inline_payload_json, byte_size)
            VALUES ('invalid', 'inline', '{}'::jsonb, 1)
        """,
        {},
    )
    _reject(
        engine,
        """
            INSERT INTO ingestion.raw_objects
                (sha256, storage_provider, inline_payload_json, byte_size)
            VALUES (:sha, 'inline', '{}'::jsonb, 2)
        """,
        {"sha": "d" * 64},
    )
    _reject(
        engine,
        """
            INSERT INTO ingestion.crawl_runs
                (source_id, run_type, trigger_type, started_at, finished_at)
            VALUES (:source_id, 'test', 'test', now(), now() - interval '1 minute')
        """,
        {"source_id": source_id},
    )


def test_lineage_constraints_and_cascade(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        source_id = _source(connection, "lineage-source")
        parser_id = connection.execute(
            sa.text(
                """
            INSERT INTO ingestion.parser_versions
                (source_id, parser_name, version, schema_version)
            VALUES (:source_id, 'fixture-parser', '1', 'direct.v1') RETURNING id
        """
            ),
            {"source_id": source_id},
        ).scalar_one()
        run_id = connection.execute(
            sa.text(
                """
            INSERT INTO ingestion.crawl_runs (source_id, run_type, trigger_type)
            VALUES (:source_id, 'test', 'test') RETURNING id
        """
            ),
            {"source_id": source_id},
        ).scalar_one()
        task_id = connection.execute(
            sa.text(
                """
            INSERT INTO ingestion.crawl_tasks (crawl_run_id, source_id, task_type, requested_url)
            VALUES (:run_id, :source_id, 'detail_page', 'https://example.test/jobs/1') RETURNING id
        """
            ),
            {"run_id": run_id, "source_id": source_id},
        ).scalar_one()
        fetch_id = connection.execute(
            sa.text(
                """
            INSERT INTO ingestion.fetch_events
                (crawl_run_id, crawl_task_id, source_id, requested_url, http_status,
                 robots_allowed, fetch_outcome, fetched_at)
            VALUES (:run_id, :task_id, :source_id, 'https://example.test/jobs/1', 200,
                    true, 'success', now()) RETURNING id
        """
            ),
            {"run_id": run_id, "task_id": task_id, "source_id": source_id},
        ).scalar_one()
        extraction_id = connection.execute(
            sa.text(
                """
            INSERT INTO ingestion.extraction_runs (crawl_run_id, fetch_event_id, parser_version_id)
            VALUES (:run_id, :fetch_id, :parser_id) RETURNING id
        """
            ),
            {"run_id": run_id, "fetch_id": fetch_id, "parser_id": parser_id},
        ).scalar_one()
        connection.execute(
            sa.text(
                """
            INSERT INTO ingestion.extracted_records
                (extraction_run_id, source_id, source_job_id, fetch_event_id,
                 record_schema_version, direct_payload_json, direct_hash, extracted_at)
            VALUES (:extraction_id, :source_id, 'job-1', :fetch_id,
                    'direct.v1', '{}'::jsonb, :direct_hash, now())
        """
            ),
            {
                "extraction_id": extraction_id,
                "source_id": source_id,
                "fetch_id": fetch_id,
                "direct_hash": "c" * 64,
            },
        )
    _reject(
        engine,
        """
            INSERT INTO ingestion.extraction_runs (fetch_event_id, parser_version_id)
            VALUES (:fetch_id, :parser_id)
        """,
        {"fetch_id": fetch_id, "parser_id": parser_id},
    )
    _reject(
        engine,
        """
            INSERT INTO ingestion.extracted_records
                (extraction_run_id, source_id, source_job_id, fetch_event_id,
                 record_schema_version, direct_payload_json, direct_hash, extracted_at)
            VALUES (:extraction_id, :source_id, 'job-1', :fetch_id,
                    'direct.v1', '{}'::jsonb, :direct_hash, now())
        """,
        {
            "extraction_id": extraction_id,
            "source_id": source_id,
            "fetch_id": fetch_id,
            "direct_hash": "e" * 64,
        },
    )
    _reject(
        engine,
        """
            INSERT INTO ingestion.extracted_records
                (extraction_run_id, source_id, source_job_id, fetch_event_id,
                 record_schema_version, direct_payload_json, direct_hash, extracted_at)
            VALUES (:extraction_id, :source_id, 'job-bad-hash', :fetch_id,
                    'direct.v1', '{}'::jsonb, 'invalid', now())
        """,
        {
            "extraction_id": extraction_id,
            "source_id": source_id,
            "fetch_id": fetch_id,
        },
    )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM ingestion.sources WHERE id=:id"), {"id": source_id})
    with engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM ingestion.crawl_runs WHERE id=:id"), {"id": run_id})
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM ingestion.crawl_tasks WHERE id=:id"), {"id": task_id}
            )
            == 0
        )
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM ingestion.fetch_events WHERE id=:id"),
                {"id": fetch_id},
            )
            == 0
        )


def test_invalid_fetch_extraction_and_error_constraints(engine: sa.Engine) -> None:
    with engine.begin() as connection:
        source_id = _source(connection, "invalid-lineage-source")
        run_id = connection.execute(
            sa.text(
                "INSERT INTO ingestion.crawl_runs (source_id, run_type, trigger_type) "
                "VALUES (:source_id, 'test', 'test') RETURNING id"
            ),
            {"source_id": source_id},
        ).scalar_one()
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                """
            INSERT INTO ingestion.fetch_events
                (crawl_run_id, source_id, requested_url, http_status, fetch_outcome, fetched_at)
            VALUES (:run_id, :source_id, 'https://example.test', 500, 'success', now())
        """
            ),
            {"run_id": run_id, "source_id": source_id},
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                """
            INSERT INTO ingestion.fetch_events
                (crawl_run_id, source_id, requested_url, http_status, fetch_outcome, fetched_at)
            VALUES (:run_id, :source_id, 'https://example.test/success-null',
                    NULL, 'success', now())
        """
            ),
            {"run_id": run_id, "source_id": source_id},
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                """
            INSERT INTO ingestion.fetch_events
                (crawl_run_id, source_id, requested_url, robots_allowed,
                 fetch_outcome, fetched_at)
            VALUES (:run_id, :source_id, 'https://example.test/robots-null',
                    NULL, 'robots_disallowed', now())
        """
            ),
            {"run_id": run_id, "source_id": source_id},
        )
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(
            sa.text(
                """
            INSERT INTO ingestion.crawl_errors
                (crawl_run_id, source_id, stage, category, sanitized_message)
            VALUES (:run_id, :source_id, 'fetch', 'unexpected', 'safe fixture error')
        """
            ),
            {"run_id": run_id, "source_id": source_id},
        )


def test_migration_002_downgrade_and_reupgrade(engine: sa.Engine) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.downgrade(config, "20260726_0001")
    inspector = sa.inspect(engine)
    assert "sources" in inspector.get_table_names(schema="ingestion")
    assert "crawl_runs" not in inspector.get_table_names(schema="ingestion")
    command.upgrade(config, "head")
    assert "crawl_runs" in sa.inspect(engine).get_table_names(schema="ingestion")
