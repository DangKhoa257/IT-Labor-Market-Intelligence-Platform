"""PostgreSQL integration tests for Database V1 Migration 004."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import cast
from uuid import UUID

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from alembic import command

DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="Database V1 history/quality integration tests require PostgreSQL",
)

HISTORY_TABLES = {
    "job_observations",
    "observation_descriptions",
    "observation_locations",
    "observation_salaries",
    "observation_skills",
    "observation_occupations",
    "job_status_events",
    "job_change_events",
    "job_repost_events",
}
QUALITY_TABLES = {
    "validation_runs",
    "data_quality_issues",
    "field_evidence",
    "duplicate_candidates",
    "duplicate_clusters",
    "duplicate_cluster_members",
}
APPEND_ONLY_TABLES = {
    "job_observations",
    "observation_descriptions",
    "observation_locations",
    "observation_salaries",
    "observation_skills",
    "observation_occupations",
    "job_status_events",
    "job_change_events",
    "job_repost_events",
    "field_evidence",
    "duplicate_candidates",
}


@pytest.fixture(scope="module")
def engine() -> Iterator[sa.Engine]:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")
    value = sa.create_engine(DATABASE_URL)
    yield value
    value.dispose()


def _uuid(connection: sa.Connection, sql: str, values: dict[str, object]) -> UUID:
    return cast(UUID, connection.execute(sa.text(sql), values).scalar_one())


def _integer(connection: sa.Connection, sql: str, values: dict[str, object]) -> int:
    return cast(int, connection.execute(sa.text(sql), values).scalar_one())


def _reject(engine: sa.Engine, sql: str, values: dict[str, object]) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(sa.text(sql), values)


def _source(connection: sa.Connection, slug: str) -> UUID:
    return _uuid(
        connection,
        """INSERT INTO ingestion.sources (slug, display_name, base_url, status)
           VALUES (:slug, :slug, 'https://example.test', 'approved') RETURNING id""",
        {"slug": slug},
    )


def _parser(connection: sa.Connection, source_id: UUID, name: str) -> UUID:
    return _uuid(
        connection,
        """INSERT INTO ingestion.parser_versions
               (source_id, parser_name, version, schema_version)
           VALUES (:source, :name, '1', 'direct.v1') RETURNING id""",
        {"source": source_id, "name": name},
    )


def _record(
    connection: sa.Connection,
    source_id: UUID,
    parser_id: UUID,
    source_job_id: str,
    suffix: str,
) -> int:
    crawl_run_id = _uuid(
        connection,
        """INSERT INTO ingestion.crawl_runs (source_id, run_type, trigger_type)
           VALUES (:source, 'test', 'test') RETURNING id""",
        {"source": source_id},
    )
    task_id = _integer(
        connection,
        """INSERT INTO ingestion.crawl_tasks
               (crawl_run_id, source_id, task_type, requested_url)
           VALUES (:run, :source, 'detail_page', :url) RETURNING id""",
        {
            "run": crawl_run_id,
            "source": source_id,
            "url": f"https://example.test/jobs/{source_job_id}/{suffix}",
        },
    )
    fetch_id = _integer(
        connection,
        """INSERT INTO ingestion.fetch_events
               (crawl_run_id, crawl_task_id, source_id, requested_url, http_status,
                robots_allowed, fetch_outcome, fetched_at)
           VALUES (:run, :task, :source, :url, 200, true, 'success', now()) RETURNING id""",
        {
            "run": crawl_run_id,
            "task": task_id,
            "source": source_id,
            "url": f"https://example.test/jobs/{source_job_id}/{suffix}",
        },
    )
    extraction_id = _integer(
        connection,
        """INSERT INTO ingestion.extraction_runs
               (crawl_run_id, fetch_event_id, parser_version_id)
           VALUES (:run, :fetch, :parser) RETURNING id""",
        {"run": crawl_run_id, "fetch": fetch_id, "parser": parser_id},
    )
    return _integer(
        connection,
        """INSERT INTO ingestion.extracted_records
               (extraction_run_id, source_id, source_job_id, fetch_event_id,
                record_schema_version, direct_payload_json, direct_hash, extracted_at)
           VALUES (:extraction, :source, :source_job_id, :fetch,
                   'direct.v1', '{}'::jsonb, :hash, now()) RETURNING id""",
        {
            "extraction": extraction_id,
            "source": source_id,
            "source_job_id": source_job_id,
            "fetch": fetch_id,
            "hash": (suffix[0].lower() if suffix[0].lower() in "abcdef" else "a") * 64,
        },
    )


def _job(connection: sa.Connection, source_id: UUID, source_job_id: str) -> UUID:
    return _uuid(
        connection,
        """INSERT INTO core.job_postings
               (source_id, source_job_id, source_url, title_raw,
                first_seen_at, last_seen_at, last_changed_at)
           VALUES (:source, :source_job_id, :url, 'EXAMPLE_NOT_REAL_DATA Engineer',
                   now(), now(), now()) RETURNING id""",
        {
            "source": source_id,
            "source_job_id": source_job_id,
            "url": f"https://example.test/jobs/{source_job_id}",
        },
    )


def _observation(
    connection: sa.Connection,
    *,
    job_id: UUID,
    source_id: UUID,
    source_job_id: str,
    record_id: int,
    canonical_hash: str,
    normalization_version: str,
    previous_id: int | None = None,
) -> int:
    return _integer(
        connection,
        """INSERT INTO history.job_observations
               (job_posting_id, source_id, source_job_id, extracted_record_id,
                previous_observation_id, observation_reason, observed_at, canonical_hash,
                status, source_url, title_raw, canonical_payload_json, normalization_version)
           VALUES (:job, :source, :source_job_id, :record, :previous, 'content_changed',
                   now(), :hash, 'active', :url, 'EXAMPLE_NOT_REAL_DATA Engineer',
                   '{}'::jsonb, :normalization) RETURNING id""",
        {
            "job": job_id,
            "source": source_id,
            "source_job_id": source_job_id,
            "record": record_id,
            "previous": previous_id,
            "hash": canonical_hash,
            "url": f"https://example.test/jobs/{source_job_id}",
            "normalization": normalization_version,
        },
    )


@pytest.fixture(scope="module")
def catalog(engine: sa.Engine) -> dict[str, UUID | int]:
    with engine.begin() as connection:
        source_a = _source(connection, "history-source-a")
        source_b = _source(connection, "history-source-b")
        parser_a = _parser(connection, source_a, "history-parser-a")
        parser_b = _parser(connection, source_b, "history-parser-b")
        job_a = _job(connection, source_a, "history-job-a")
        job_b = _job(connection, source_a, "history-job-b")
        records = {
            "record_a1": _record(connection, source_a, parser_a, "history-job-a", "a1"),
            "record_a2": _record(connection, source_a, parser_a, "history-job-a", "b2"),
            "record_a3": _record(connection, source_a, parser_a, "history-job-a", "c3"),
            "record_b1": _record(connection, source_a, parser_a, "history-job-b", "d1"),
            "record_wrong_source": _record(connection, source_b, parser_b, "history-job-a", "e1"),
        }
        observation_a1 = _observation(
            connection,
            job_id=job_a,
            source_id=source_a,
            source_job_id="history-job-a",
            record_id=records["record_a1"],
            canonical_hash="a" * 64,
            normalization_version="history.v1",
        )
        observation_a2 = _observation(
            connection,
            job_id=job_a,
            source_id=source_a,
            source_job_id="history-job-a",
            record_id=records["record_a2"],
            canonical_hash="b" * 64,
            normalization_version="history.v1",
            previous_id=observation_a1,
        )
        observation_a3 = _observation(
            connection,
            job_id=job_a,
            source_id=source_a,
            source_job_id="history-job-a",
            record_id=records["record_a3"],
            canonical_hash="a" * 64,
            normalization_version="history.v1",
            previous_id=observation_a2,
        )
        observation_b1 = _observation(
            connection,
            job_id=job_b,
            source_id=source_a,
            source_job_id="history-job-b",
            record_id=records["record_b1"],
            canonical_hash="d" * 64,
            normalization_version="history.v1",
        )
        location_a = _uuid(
            connection,
            """INSERT INTO core.locations
                   (resolution_key, location_type, country_code,
                    canonical_label, normalized_label)
               VALUES ('history-location-a', 'city', 'VN',
                       'EXAMPLE_NOT_REAL_DATA City A', 'example city a') RETURNING id""",
            {},
        )
        location_b = _uuid(
            connection,
            """INSERT INTO core.locations
                   (resolution_key, location_type, country_code,
                    canonical_label, normalized_label)
               VALUES ('history-location-b', 'remote_scope', 'VN',
                       'EXAMPLE_NOT_REAL_DATA Remote', 'example remote') RETURNING id""",
            {},
        )
        skill_version = _uuid(
            connection,
            """INSERT INTO taxonomy.taxonomy_versions (taxonomy_type, version, name)
               VALUES ('skill', 'SYNTHETIC_HISTORY.v1',
                       'EXAMPLE_NOT_REAL_DATA history skills') RETURNING id""",
            {},
        )
        occupation_version = _uuid(
            connection,
            """INSERT INTO taxonomy.taxonomy_versions (taxonomy_type, version, name)
               VALUES ('occupation', 'SYNTHETIC_HISTORY.v1',
                       'EXAMPLE_NOT_REAL_DATA history occupations') RETURNING id""",
            {},
        )
        skill = _uuid(
            connection,
            """INSERT INTO taxonomy.skills
                   (taxonomy_version_id, canonical_code, canonical_name, normalized_name)
               VALUES (:version, 'history-skill', 'EXAMPLE_NOT_REAL_DATA Skill',
                       'example skill') RETURNING id""",
            {"version": skill_version},
        )
        occupation = _uuid(
            connection,
            """INSERT INTO taxonomy.occupations
                   (taxonomy_version_id, canonical_code, canonical_name, normalized_name)
               VALUES (:version, 'history-occupation', 'EXAMPLE_NOT_REAL_DATA Occupation',
                       'example occupation') RETURNING id""",
            {"version": occupation_version},
        )
        occupation_2 = _uuid(
            connection,
            """INSERT INTO taxonomy.occupations
                   (taxonomy_version_id, canonical_code, canonical_name, normalized_name)
               VALUES (:version, 'history-occupation-2',
                       'EXAMPLE_NOT_REAL_DATA Occupation 2', 'example occupation 2')
               RETURNING id""",
            {"version": occupation_version},
        )
    return {
        "source_a": source_a,
        "source_b": source_b,
        "job_a": job_a,
        "job_b": job_b,
        "observation_a1": observation_a1,
        "observation_a2": observation_a2,
        "observation_a3": observation_a3,
        "observation_b1": observation_b1,
        "location_a": location_a,
        "location_b": location_b,
        "skill": skill,
        "occupation": occupation,
        "occupation_2": occupation_2,
        **records,
    }


def test_schema_inventory_and_head(engine: sa.Engine) -> None:
    inspector = sa.inspect(engine)
    assert set(inspector.get_table_names(schema="history")) == HISTORY_TABLES
    assert set(inspector.get_table_names(schema="quality")) == QUALITY_TABLES
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == (
            "20260727_0004"
        )


def test_observation_identity_lineage_hashes_and_current_pointer(
    engine: sa.Engine, catalog: dict[str, UUID | int]
) -> None:
    with engine.begin() as connection:
        hashes = list(
            connection.scalars(
                sa.text(
                    """SELECT canonical_hash FROM history.job_observations
                       WHERE job_posting_id=:job ORDER BY id"""
                ),
                {"job": catalog["job_a"]},
            )
        )
        assert hashes == ["a" * 64, "b" * 64, "a" * 64]
        connection.execute(
            sa.text(
                """UPDATE core.job_postings SET current_observation_id=:observation
                   WHERE id=:job"""
            ),
            {"observation": catalog["observation_a3"], "job": catalog["job_a"]},
        )
        count_before = connection.scalar(
            sa.text("SELECT count(*) FROM history.job_observations WHERE job_posting_id=:job"),
            {"job": catalog["job_a"]},
        )
        connection.execute(
            sa.text("UPDATE core.job_postings SET last_seen_at=now() WHERE id=:job"),
            {"job": catalog["job_a"]},
        )
        count_after = connection.scalar(
            sa.text("SELECT count(*) FROM history.job_observations WHERE job_posting_id=:job"),
            {"job": catalog["job_a"]},
        )
        assert count_after == count_before

    _reject(
        engine,
        """UPDATE core.job_postings SET current_observation_id=:observation WHERE id=:job""",
        {"observation": catalog["observation_b1"], "job": catalog["job_a"]},
    )
    _reject(
        engine,
        """INSERT INTO history.job_observations
               (job_posting_id, source_id, source_job_id, extracted_record_id,
                observation_reason, observed_at, canonical_hash, status, source_url,
                title_raw, normalization_version)
           VALUES (:job, :source, 'history-job-a', :record, 'first_seen', now(),
                   :hash, 'active', 'https://example.test/jobs/a', 'Title', 'wrong-source')""",
        {
            "job": catalog["job_a"],
            "source": catalog["source_b"],
            "record": catalog["record_wrong_source"],
            "hash": "e" * 64,
        },
    )
    _reject(
        engine,
        """INSERT INTO history.job_observations
               (job_posting_id, source_id, source_job_id, extracted_record_id,
                observation_reason, observed_at, canonical_hash, status, source_url,
                title_raw, normalization_version)
           VALUES (:job, :source, 'history-job-a', :record, 'first_seen', now(),
                   :hash, 'active', 'https://example.test/jobs/a', 'Title', 'wrong-job')""",
        {
            "job": catalog["job_a"],
            "source": catalog["source_a"],
            "record": catalog["record_b1"],
            "hash": "d" * 64,
        },
    )
    _reject(
        engine,
        """INSERT INTO history.job_observations
               (job_posting_id, source_id, source_job_id, extracted_record_id,
                previous_observation_id, observation_reason, observed_at, canonical_hash,
                status, source_url, title_raw, normalization_version)
           VALUES (:job, :source, 'history-job-a', :record, :previous, 'reprocessed', now(),
                   :hash, 'active', 'https://example.test/jobs/a', 'Title', 'history.v2')""",
        {
            "job": catalog["job_a"],
            "source": catalog["source_a"],
            "record": catalog["record_a3"],
            "previous": catalog["observation_b1"],
            "hash": "a" * 64,
        },
    )
    _reject(
        engine,
        """INSERT INTO history.job_observations
               (job_posting_id, source_id, source_job_id, extracted_record_id,
                observation_reason, observed_at, canonical_hash, status, source_url,
                title_raw, normalization_version)
           VALUES (:job, :source, 'history-job-a', :record, 'reprocessed', now(),
                   :hash, 'active', 'https://example.test/jobs/a', 'Title', 'history.v1')""",
        {
            "job": catalog["job_a"],
            "source": catalog["source_a"],
            "record": catalog["record_a1"],
            "hash": "a" * 64,
        },
    )
    for suffix, canonical_hash, extra_columns, extra_values in (
        ("hash", "invalid", "", ""),
        ("payload", "a" * 64, ", canonical_payload_json", ", '[]'::jsonb"),
        ("experience", "a" * 64, ", experience_min_years, experience_max_years", ", 2, 1"),
    ):
        _reject(
            engine,
            f"""INSERT INTO history.job_observations
                    (job_posting_id, source_id, source_job_id, extracted_record_id,
                     observation_reason, observed_at, canonical_hash, status, source_url,
                     title_raw, normalization_version{extra_columns})
                VALUES (:job, :source, 'history-job-a', :record, 'reprocessed', now(),
                        :hash, 'active', 'https://example.test/jobs/a', 'Title',
                        :normalization{extra_values})""",
            {
                "job": catalog["job_a"],
                "source": catalog["source_a"],
                "record": catalog["record_a1"],
                "hash": canonical_hash,
                "normalization": f"invalid-{suffix}",
            },
        )


def test_historical_children_constraints(engine: sa.Engine, catalog: dict[str, UUID | int]) -> None:
    with engine.begin() as connection:
        description_id = _integer(
            connection,
            """INSERT INTO history.observation_locations
                   (observation_id, location_id, relationship_type, is_primary)
               VALUES (:observation, :location, 'workplace', true) RETURNING id""",
            {
                "observation": catalog["observation_a1"],
                "location": catalog["location_a"],
            },
        )
        remote_location_id = _integer(
            connection,
            """INSERT INTO history.observation_locations
                   (observation_id, location_id, relationship_type,
                    is_remote, remote_scope)
               VALUES (:observation, :location, 'applicant_eligible', true, 'vietnam')
               RETURNING id""",
            {
                "observation": catalog["observation_a1"],
                "location": catalog["location_b"],
            },
        )
        connection.execute(
            sa.text(
                """INSERT INTO history.observation_descriptions
                       (observation_id, description_text, content_hash)
                   VALUES (:observation, 'EXAMPLE_NOT_REAL_DATA description', :hash)"""
            ),
            {"observation": catalog["observation_a1"], "hash": "f" * 64},
        )
        for offer_index, period, amount in ((0, "month", 1000), (1, "year", 12000)):
            connection.execute(
                sa.text(
                    """INSERT INTO history.observation_salaries
                           (observation_id, offer_index, amount_min, currency, period,
                            is_disclosed)
                       VALUES (:observation, :offer_index, :amount, 'USD', :period, true)"""
                ),
                {
                    "observation": catalog["observation_a1"],
                    "offer_index": offer_index,
                    "amount": amount,
                    "period": period,
                },
            )
        for requirement_type in ("required", "preferred"):
            connection.execute(
                sa.text(
                    """INSERT INTO history.observation_skills
                           (observation_id, skill_id, requirement_type)
                       VALUES (:observation, :skill, :requirement_type)"""
                ),
                {
                    "observation": catalog["observation_a1"],
                    "skill": catalog["skill"],
                    "requirement_type": requirement_type,
                },
            )
        occupation_row_id = _integer(
            connection,
            """INSERT INTO history.observation_occupations
                   (observation_id, occupation_id, is_primary)
               VALUES (:observation, :occupation, true) RETURNING id""",
            {
                "observation": catalog["observation_a1"],
                "occupation": catalog["occupation"],
            },
        )
        assert {description_id, remote_location_id, occupation_row_id}

    _reject(
        engine,
        """INSERT INTO history.observation_locations
               (observation_id, location_id, relationship_type, is_primary)
           VALUES (:observation, :location, 'workplace', true)""",
        {
            "observation": catalog["observation_a1"],
            "location": catalog["location_b"],
        },
    )
    for is_remote, remote_scope in (("true", "NULL"), ("false", "'worldwide'")):
        _reject(
            engine,
            f"""INSERT INTO history.observation_locations
                    (observation_id, location_id, relationship_type, is_remote, remote_scope)
                VALUES (:observation, :location, 'other', {is_remote}, {remote_scope})""",
            {
                "observation": catalog["observation_a2"],
                "location": catalog["location_a"],
            },
        )
    for columns, values in (
        ("is_disclosed", "true"),
        ("fx_rate_date", "'2026-01-01'"),
        ("amount_min, amount_max, is_disclosed", "2, 1, true"),
    ):
        _reject(
            engine,
            f"""INSERT INTO history.observation_salaries
                    (observation_id, offer_index, {columns})
                VALUES (:observation, 10, {values})""",
            {"observation": catalog["observation_a2"]},
        )
    _reject(
        engine,
        """INSERT INTO history.observation_occupations
               (observation_id, occupation_id, is_primary)
           VALUES (:observation, :occupation, true)""",
        {
            "observation": catalog["observation_a1"],
            "occupation": catalog["occupation_2"],
        },
    )
    for description_text, status, content_hash in (
        ("NULL", "'not_required'", "'" + "a" * 64 + "'"),
        ("'   '", "'not_required'", "'" + "b" * 64 + "'"),
        ("NULL", "'redacted'", "'invalid'"),
    ):
        _reject(
            engine,
            f"""INSERT INTO history.observation_descriptions
                    (observation_id, description_text, redaction_status, content_hash)
                VALUES (:observation, {description_text}, {status}, {content_hash})""",
            {"observation": catalog["observation_a2"]},
        )
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """INSERT INTO history.observation_descriptions
                       (observation_id, description_text, redaction_status, content_hash)
                   VALUES (:observation, NULL, 'redacted', :hash)"""
            ),
            {"observation": catalog["observation_a2"], "hash": "c" * 64},
        )


def test_events_and_same_job_constraints(engine: sa.Engine, catalog: dict[str, UUID | int]) -> None:
    with engine.begin() as connection:
        status_event_id = _integer(
            connection,
            """INSERT INTO history.job_status_events
                   (job_posting_id, observation_id, from_status, to_status,
                    event_type, event_at)
               VALUES (:job, :observation, NULL, 'active', 'first_seen', now()) RETURNING id""",
            {"job": catalog["job_a"], "observation": catalog["observation_a1"]},
        )
        change_event_id = _integer(
            connection,
            """INSERT INTO history.job_change_events
                   (job_posting_id, from_observation_id, to_observation_id, field_path,
                    change_type, old_value_json, new_value_json, detected_at)
               VALUES (:job, :from_observation, :to_observation, 'title_normalized',
                       'field_changed', '"old"'::jsonb, '"new"'::jsonb, now()) RETURNING id""",
            {
                "job": catalog["job_a"],
                "from_observation": catalog["observation_a1"],
                "to_observation": catalog["observation_a2"],
            },
        )
        repost_event_id = _integer(
            connection,
            """INSERT INTO history.job_repost_events
                   (job_posting_id, previous_observation_id, new_observation_id,
                    repost_type, detection_method, method_version, detected_at)
               VALUES (:job, :previous, :new, 'content_refresh',
                       'EXAMPLE_NOT_REAL_DATA manual rule', 'history.v1', now()) RETURNING id""",
            {
                "job": catalog["job_a"],
                "previous": catalog["observation_a2"],
                "new": catalog["observation_a3"],
            },
        )
        assert {status_event_id, change_event_id, repost_event_id}

    _reject(
        engine,
        """INSERT INTO history.job_status_events
               (job_posting_id, from_status, to_status, event_type, event_at)
           VALUES (:job, 'active', 'active', 'other', now())""",
        {"job": catalog["job_a"]},
    )
    _reject(
        engine,
        """INSERT INTO history.job_status_events
               (job_posting_id, observation_id, to_status, event_type, event_at)
           VALUES (:job, :observation, 'active', 'first_seen', now())""",
        {"job": catalog["job_a"], "observation": catalog["observation_b1"]},
    )
    _reject(
        engine,
        """INSERT INTO history.job_change_events
               (job_posting_id, from_observation_id, to_observation_id, field_path,
                change_type, old_value_json, new_value_json, detected_at)
           VALUES (:job, :from_observation, :to_observation, 'title', 'field_changed',
                   '"same"'::jsonb, '"same"'::jsonb, now())""",
        {
            "job": catalog["job_a"],
            "from_observation": catalog["observation_a1"],
            "to_observation": catalog["observation_a2"],
        },
    )
    _reject(
        engine,
        """INSERT INTO history.job_repost_events
               (job_posting_id, previous_observation_id, new_observation_id,
                repost_type, detection_method, method_version, detected_at)
           VALUES (:job, :previous, :new, 'other', 'manual', 'cross-job', now())""",
        {
            "job": catalog["job_a"],
            "previous": catalog["observation_a1"],
            "new": catalog["observation_b1"],
        },
    )


def test_quality_lifecycle_evidence_and_advisory_duplicates(
    engine: sa.Engine, catalog: dict[str, UUID | int]
) -> None:
    with engine.begin() as connection:
        validation_run_id = _uuid(
            connection,
            """INSERT INTO quality.validation_runs
                   (source_id, scope_type, ruleset_version, status, started_at,
                    finished_at, records_checked_count, issues_found_count,
                    critical_issue_count)
               VALUES (:source, 'observation', 'quality.v1', 'succeeded',
                       now() - interval '1 minute', now(), 3, 1, 0) RETURNING id""",
            {"source": catalog["source_a"]},
        )
        issue_id = _integer(
            connection,
            """INSERT INTO quality.data_quality_issues
                   (validation_run_id, job_posting_id, observation_id, issue_code,
                    fingerprint, message, rule_version)
               VALUES (:run, :job, :observation, 'EXAMPLE_FIELD_WARNING', :fingerprint,
                       'EXAMPLE_NOT_REAL_DATA quality issue', 'quality.v1') RETURNING id""",
            {
                "run": validation_run_id,
                "job": catalog["job_a"],
                "observation": catalog["observation_a1"],
                "fingerprint": "1" * 64,
            },
        )
        connection.execute(
            sa.text(
                """UPDATE quality.data_quality_issues
                   SET status='resolved', reviewed_by='EXAMPLE_NOT_REAL_DATA reviewer',
                       reviewed_at=now(), resolved_at=now(),
                       resolution_notes='EXAMPLE_NOT_REAL_DATA resolved'
                   WHERE id=:issue"""
            ),
            {"issue": issue_id},
        )
        field_evidence_id = _integer(
            connection,
            """INSERT INTO quality.field_evidence
                   (observation_id, field_path, classification, normalized_value_json,
                    normalization_rule, normalization_version)
               VALUES (:observation, 'title_normalized', 'normalized',
                       '"Example Engineer"'::jsonb, 'trim_casefold', 'quality.v1')
               RETURNING id""",
            {"observation": catalog["observation_a1"]},
        )
        left_job, right_job = sorted((cast(UUID, catalog["job_a"]), cast(UUID, catalog["job_b"])))
        duplicate_candidate_id = _integer(
            connection,
            """INSERT INTO quality.duplicate_candidates
                   (left_job_posting_id, right_job_posting_id, candidate_reason,
                    method_version, score)
               VALUES (:left_job, :right_job, 'manual', 'quality.v1', 0.7500) RETURNING id""",
            {"left_job": left_job, "right_job": right_job},
        )
        cluster_id = _uuid(
            connection,
            """INSERT INTO quality.duplicate_clusters
                   (cluster_type, method_version, score)
               VALUES ('possible_duplicate', 'quality.v1', 0.7500) RETURNING id""",
            {},
        )
        connection.execute(
            sa.text(
                """INSERT INTO quality.duplicate_cluster_members
                       (cluster_id, job_posting_id, member_role)
                   VALUES (:cluster, :job, 'representative')"""
            ),
            {"cluster": cluster_id, "job": catalog["job_a"]},
        )
    for statement in (
        """INSERT INTO quality.validation_runs
               (scope_type, ruleset_version, status, issues_found_count, critical_issue_count)
           VALUES ('batch', 'quality.v1', 'pending', 0, 1)""",
        """INSERT INTO quality.validation_runs
               (scope_type, ruleset_version, status)
           VALUES ('batch', 'quality.v1', 'succeeded')""",
    ):
        _reject(engine, statement, {})
    _reject(
        engine,
        """INSERT INTO quality.data_quality_issues
               (validation_run_id, issue_code, fingerprint, message, rule_version)
           VALUES (:run, 'NO_CONTEXT', :fingerprint, 'No context', 'quality.v1')""",
        {"run": validation_run_id, "fingerprint": "2" * 64},
    )
    _reject(
        engine,
        """INSERT INTO quality.data_quality_issues
               (validation_run_id, job_posting_id, issue_code, fingerprint,
                message, rule_version)
           VALUES (:run, :job, 'DUPLICATE', :fingerprint, 'Duplicate', 'quality.v1')""",
        {
            "run": validation_run_id,
            "job": catalog["job_a"],
            "fingerprint": "1" * 64,
        },
    )
    _reject(
        engine,
        """INSERT INTO quality.data_quality_issues
               (validation_run_id, job_posting_id, issue_code, fingerprint, message,
                rule_version, status)
           VALUES (:run, :job, 'BAD_RESOLUTION', :fingerprint, 'Bad resolution',
                   'quality.v1', 'resolved')""",
        {
            "run": validation_run_id,
            "job": catalog["job_a"],
            "fingerprint": "3" * 64,
        },
    )
    for classification, extra_columns, extra_values in (
        ("not_available", ", raw_value_json", ", '1'::jsonb"),
        ("inferred", ", raw_value_json", ", '1'::jsonb"),
        ("normalized", ", normalized_value_json", ", '1'::jsonb"),
        ("direct_html", "", ""),
    ):
        _reject(
            engine,
            f"""INSERT INTO quality.field_evidence
                    (observation_id, field_path, classification{extra_columns})
                VALUES (:observation, :field_path, :classification{extra_values})""",
            {
                "observation": catalog["observation_a2"],
                "field_path": f"invalid.{classification}",
                "classification": classification,
            },
        )
    left_job, right_job = sorted((cast(UUID, catalog["job_a"]), cast(UUID, catalog["job_b"])))
    _reject(
        engine,
        """INSERT INTO quality.duplicate_candidates
               (left_job_posting_id, right_job_posting_id, candidate_reason,
                method_version, score)
           VALUES (:left_job, :right_job, 'manual', 'wrong-order', 0.5)""",
        {"left_job": right_job, "right_job": left_job},
    )
    _reject(
        engine,
        """INSERT INTO quality.duplicate_cluster_members
               (cluster_id, job_posting_id, member_role)
           VALUES (:cluster, :job, 'representative')""",
        {"cluster": cluster_id, "job": catalog["job_b"]},
    )
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """INSERT INTO quality.duplicate_cluster_members
                       (cluster_id, job_posting_id, member_role)
                   VALUES (:cluster, :job, 'member')"""
            ),
            {"cluster": cluster_id, "job": catalog["job_b"]},
        )
        connection.execute(
            sa.text("DELETE FROM quality.duplicate_clusters WHERE id=:cluster"),
            {"cluster": cluster_id},
        )
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM core.job_postings WHERE id IN (:a, :b)"),
                {"a": catalog["job_a"], "b": catalog["job_b"]},
            )
            == 2
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM quality.duplicate_cluster_members "
                    "WHERE cluster_id=:cluster"
                ),
                {"cluster": cluster_id},
            )
            == 0
        )
        assert {field_evidence_id, duplicate_candidate_id}


def test_append_only_enforcement_and_trigger_inventory(
    engine: sa.Engine, catalog: dict[str, UUID | int]
) -> None:
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                """SELECT event_object_table, trigger_name
                   FROM information_schema.triggers
                   WHERE trigger_schema IN ('history', 'quality')
                     AND trigger_name LIKE 'trg_%__append_only'"""
            )
        ).all()
    assert {row[0] for row in rows} == APPEND_ONLY_TABLES

    mutations = (
        (
            "history.job_observations",
            "id",
            catalog["observation_a1"],
            "status='closed'",
        ),
        (
            "history.observation_locations",
            "observation_id",
            catalog["observation_a1"],
            "source_text='changed'",
        ),
        (
            "history.job_status_events",
            "observation_id",
            catalog["observation_a1"],
            "rule_version='changed'",
        ),
        (
            "quality.field_evidence",
            "observation_id",
            catalog["observation_a1"],
            "review_status='verified'",
        ),
    )
    for table, key, value, assignment in mutations:
        _reject(engine, f"UPDATE {table} SET {assignment} WHERE {key}=:value", {"value": value})
        _reject(engine, f"DELETE FROM {table} WHERE {key}=:value", {"value": value})
    with engine.connect() as connection:
        candidate_id = connection.scalar(
            sa.text("SELECT min(id) FROM quality.duplicate_candidates")
        )
        change_event_id = connection.scalar(
            sa.text("SELECT min(id) FROM history.job_change_events")
        )
    assert candidate_id is not None
    assert change_event_id is not None
    _reject(
        engine,
        "UPDATE quality.duplicate_candidates SET score=0.1 WHERE id=:id",
        {"id": candidate_id},
    )
    _reject(
        engine,
        "DELETE FROM quality.duplicate_candidates WHERE id=:id",
        {"id": candidate_id},
    )
    _reject(
        engine,
        "UPDATE history.job_change_events SET field_path='changed' WHERE id=:id",
        {"id": change_event_id},
    )
    _reject(
        engine,
        "DELETE FROM history.job_change_events WHERE id=:id",
        {"id": change_event_id},
    )


def test_zz_migration_004_downgrade_and_reupgrade(engine: sa.Engine) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.downgrade(config, "20260726_0003")
    inspector = sa.inspect(engine)
    assert "job_postings" in inspector.get_table_names(schema="core")
    assert "extracted_records" in inspector.get_table_names(schema="ingestion")
    assert "history" not in inspector.get_schema_names()
    assert "quality" not in inspector.get_schema_names()
    core_columns = {
        column["name"] for column in inspector.get_columns("job_postings", schema="core")
    }
    assert "current_observation_id" not in core_columns
    extracted_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("extracted_records", schema="ingestion")
    }
    assert "uq_extracted_records__id_source_identity" in extracted_constraints
    command.upgrade(config, "head")
    assert set(sa.inspect(engine).get_table_names(schema="history")) == HISTORY_TABLES
