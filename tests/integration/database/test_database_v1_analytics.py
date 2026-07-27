"""PostgreSQL integration tests for Database V1 Migration 005."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date
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
    reason="Database V1 analytics integration tests require PostgreSQL",
)

ANALYTICS_TABLES = {
    "refresh_runs",
    "dim_dates",
    "dim_sources",
    "dim_companies",
    "dim_locations",
    "dim_occupations",
    "dim_skills",
    "fact_job_observations",
    "fact_salary_observations",
    "bridge_job_observation_locations",
    "bridge_job_observation_occupations",
    "bridge_job_observation_skills",
    "daily_market_metrics",
    "daily_company_hiring",
    "daily_location_demand",
    "daily_occupation_demand",
    "daily_skill_demand",
    "daily_salary_metrics",
}


@pytest.fixture(scope="module")
def engine() -> Iterator[sa.Engine]:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")
    value = sa.create_engine(DATABASE_URL)
    yield value
    value.dispose()


def _one(connection: sa.Connection, sql: str, values: dict[str, object]) -> object:
    return connection.execute(sa.text(sql), values).scalar_one()


def _reject(engine: sa.Engine, sql: str, values: dict[str, object]) -> None:
    with pytest.raises(IntegrityError), engine.begin() as connection:
        connection.execute(sa.text(sql), values)


@pytest.fixture(scope="module")
def catalog(engine: sa.Engine) -> dict[str, object]:
    with engine.begin() as connection:
        source_id = cast(
            UUID,
            _one(
                connection,
                """INSERT INTO ingestion.sources
                       (slug, display_name, base_url, status, is_enabled, country_code)
                   VALUES ('analytics-example-source', 'EXAMPLE_NOT_REAL_DATA source',
                           'https://example.test', 'approved', true, 'VN') RETURNING id""",
                {},
            ),
        )
        parser_id = cast(
            UUID,
            _one(
                connection,
                """INSERT INTO ingestion.parser_versions
                       (source_id, parser_name, version, schema_version)
                   VALUES (:source, 'analytics-example-parser', '1', 'direct.v1')
                   RETURNING id""",
                {"source": source_id},
            ),
        )
        crawl_id = cast(
            UUID,
            _one(
                connection,
                """INSERT INTO ingestion.crawl_runs (source_id, run_type, trigger_type)
                   VALUES (:source, 'test', 'test') RETURNING id""",
                {"source": source_id},
            ),
        )
        task_id = cast(
            int,
            _one(
                connection,
                """INSERT INTO ingestion.crawl_tasks
                       (crawl_run_id, source_id, task_type, requested_url)
                   VALUES (:run, :source, 'detail_page', 'https://example.test/jobs/analytics')
                   RETURNING id""",
                {"run": crawl_id, "source": source_id},
            ),
        )
        fetch_id = cast(
            int,
            _one(
                connection,
                """INSERT INTO ingestion.fetch_events
                       (crawl_run_id, crawl_task_id, source_id, requested_url, http_status,
                        robots_allowed, fetch_outcome, fetched_at)
                   VALUES (:run, :task, :source, 'https://example.test/jobs/analytics',
                           200, true, 'success', '2026-01-15T08:00:00Z') RETURNING id""",
                {"run": crawl_id, "task": task_id, "source": source_id},
            ),
        )
        extraction_id = cast(
            int,
            _one(
                connection,
                """INSERT INTO ingestion.extraction_runs
                       (crawl_run_id, fetch_event_id, parser_version_id)
                   VALUES (:run, :fetch, :parser) RETURNING id""",
                {"run": crawl_id, "fetch": fetch_id, "parser": parser_id},
            ),
        )
        record_id = cast(
            int,
            _one(
                connection,
                """INSERT INTO ingestion.extracted_records
                       (extraction_run_id, source_id, source_job_id, fetch_event_id,
                        record_schema_version, direct_payload_json, direct_hash, extracted_at)
                   VALUES (:extraction, :source, 'analytics-job', :fetch, 'direct.v1',
                           '{}'::jsonb, :hash, '2026-01-15T08:01:00Z') RETURNING id""",
                {
                    "extraction": extraction_id,
                    "source": source_id,
                    "fetch": fetch_id,
                    "hash": "a" * 64,
                },
            ),
        )
        location_id = cast(
            UUID,
            _one(
                connection,
                """INSERT INTO core.locations
                       (resolution_key, location_type, country_code, locality,
                        canonical_label, normalized_label)
                   VALUES ('analytics-example-city', 'city', 'VN',
                           'EXAMPLE_NOT_REAL_DATA City', 'EXAMPLE_NOT_REAL_DATA City',
                           'example city') RETURNING id""",
                {},
            ),
        )
        company_id = cast(
            UUID,
            _one(
                connection,
                """INSERT INTO core.companies
                       (canonical_name, normalized_name, headquarters_location_id)
                   VALUES ('EXAMPLE_NOT_REAL_DATA Analytics Company',
                           'analytics example company', :location)
                   RETURNING id""",
                {"location": location_id},
            ),
        )
        job_id = cast(
            UUID,
            _one(
                connection,
                """INSERT INTO core.job_postings
                       (source_id, source_job_id, source_url, title_raw, company_id,
                        first_seen_at, last_seen_at, last_changed_at)
                   VALUES (:source, 'analytics-job', 'https://example.test/jobs/analytics',
                           'EXAMPLE_NOT_REAL_DATA Engineer', :company,
                           '2026-01-15T08:00:00Z', '2026-01-15T08:00:00Z',
                           '2026-01-15T08:00:00Z') RETURNING id""",
                {"source": source_id, "company": company_id},
            ),
        )
        occupation_version = cast(
            UUID,
            _one(
                connection,
                """INSERT INTO taxonomy.taxonomy_versions (taxonomy_type, version, name)
                   VALUES ('occupation', 'SYNTHETIC_ANALYTICS.v1',
                           'EXAMPLE_NOT_REAL_DATA occupations') RETURNING id""",
                {},
            ),
        )
        skill_version = cast(
            UUID,
            _one(
                connection,
                """INSERT INTO taxonomy.taxonomy_versions (taxonomy_type, version, name)
                   VALUES ('skill', 'SYNTHETIC_ANALYTICS.v1',
                           'EXAMPLE_NOT_REAL_DATA skills') RETURNING id""",
                {},
            ),
        )
        occupation_id = cast(
            UUID,
            _one(
                connection,
                """INSERT INTO taxonomy.occupations
                       (taxonomy_version_id, canonical_code, canonical_name, normalized_name)
                   VALUES (:version, 'analytics-occupation',
                           'EXAMPLE_NOT_REAL_DATA Occupation', 'example occupation')
                   RETURNING id""",
                {"version": occupation_version},
            ),
        )
        occupation_2_id = cast(
            UUID,
            _one(
                connection,
                """INSERT INTO taxonomy.occupations
                       (taxonomy_version_id, canonical_code, canonical_name, normalized_name)
                   VALUES (:version, 'analytics-occupation-2',
                           'EXAMPLE_NOT_REAL_DATA Occupation 2', 'example occupation 2')
                   RETURNING id""",
                {"version": occupation_version},
            ),
        )
        skill_id = cast(
            UUID,
            _one(
                connection,
                """INSERT INTO taxonomy.skills
                       (taxonomy_version_id, canonical_code, canonical_name, normalized_name)
                   VALUES (:version, 'analytics-skill', 'EXAMPLE_NOT_REAL_DATA Skill',
                           'example skill') RETURNING id""",
                {"version": skill_version},
            ),
        )
        observation_id = cast(
            int,
            _one(
                connection,
                """INSERT INTO history.job_observations
                       (job_posting_id, source_id, source_job_id, extracted_record_id,
                        crawl_run_id, observation_reason, observed_at, canonical_hash,
                        status, source_url, title_raw, company_id, employment_type_code,
                        seniority_level_code, work_mode, posted_at, canonical_payload_json,
                        normalization_version)
                   VALUES (:job, :source, 'analytics-job', :record, :crawl, 'first_seen',
                           '2026-01-15T08:00:00Z', :hash, 'active',
                           'https://example.test/jobs/analytics',
                           'EXAMPLE_NOT_REAL_DATA Engineer', :company, 'full_time', 'mid',
                           'remote', '2026-01-14T00:00:00Z', '{}'::jsonb, 'analytics.v1')
                   RETURNING id""",
                {
                    "job": job_id,
                    "source": source_id,
                    "record": record_id,
                    "crawl": crawl_id,
                    "hash": "b" * 64,
                    "company": company_id,
                },
            ),
        )
        salary_id = cast(
            int,
            _one(
                connection,
                """INSERT INTO history.observation_salaries
                       (observation_id, offer_index, amount_min, amount_max, currency,
                        period, tax_basis, is_disclosed, normalized_monthly_min,
                        normalized_monthly_max)
                   VALUES (:observation, 0, 1000, 2000, 'USD', 'month', 'gross', true,
                           1000, 2000) RETURNING id""",
                {"observation": observation_id},
            ),
        )
        null_salary_id = cast(
            int,
            _one(
                connection,
                """INSERT INTO history.observation_salaries
                       (observation_id, offer_index, is_disclosed)
                   VALUES (:observation, 1, false) RETURNING id""",
                {"observation": observation_id},
            ),
        )
        observation_location_id = cast(
            int,
            _one(
                connection,
                """INSERT INTO history.observation_locations
                       (observation_id, location_id, relationship_type, is_primary,
                        is_remote, remote_scope)
                   VALUES (:observation, :location, 'workplace', true, true, 'vietnam')
                   RETURNING id""",
                {"observation": observation_id, "location": location_id},
            ),
        )
        observation_occupation_id = cast(
            int,
            _one(
                connection,
                """INSERT INTO history.observation_occupations
                       (observation_id, occupation_id, is_primary)
                   VALUES (:observation, :occupation, true) RETURNING id""",
                {"observation": observation_id, "occupation": occupation_id},
            ),
        )
        observation_occupation_2_id = cast(
            int,
            _one(
                connection,
                """INSERT INTO history.observation_occupations
                       (observation_id, occupation_id, is_primary)
                   VALUES (:observation, :occupation, false) RETURNING id""",
                {"observation": observation_id, "occupation": occupation_2_id},
            ),
        )
        skill_rows = list(
            connection.execute(
                sa.text(
                    """INSERT INTO history.observation_skills
                           (observation_id, skill_id, requirement_type)
                       VALUES (:observation, :skill, 'required'),
                              (:observation, :skill, 'preferred') RETURNING id"""
                ),
                {"observation": observation_id, "skill": skill_id},
            ).scalars()
        )
        refresh_id = cast(
            UUID,
            _one(
                connection,
                """INSERT INTO analytics.refresh_runs
                       (run_type, status, calculation_version, window_start_date,
                        window_end_date, trigger_type, started_at, finished_at, source_id)
                   VALUES ('test', 'succeeded', 'analytics-test.v1', '2026-01-01',
                           '2026-01-31', 'test', '2026-01-16T00:00:00Z',
                           '2026-01-16T00:01:00Z', :source) RETURNING id""",
                {"source": source_id},
            ),
        )
        source_key = cast(
            int,
            _one(
                connection,
                """INSERT INTO analytics.dim_sources
                       (source_id, slug, display_name, source_type, country_code,
                        status, is_enabled, source_updated_at)
                   SELECT id, slug, display_name, source_type, country_code, status,
                          is_enabled, updated_at FROM ingestion.sources WHERE id=:source
                   RETURNING source_key""",
                {"source": source_id},
            ),
        )
        company_key = cast(
            int,
            _one(
                connection,
                """INSERT INTO analytics.dim_companies
                       (company_id, canonical_name, normalized_name, company_type,
                        headquarters_location_id, resolution_status, company_updated_at)
                   SELECT id, canonical_name, normalized_name, company_type,
                          headquarters_location_id, resolution_status, updated_at
                   FROM core.companies WHERE id=:company RETURNING company_key""",
                {"company": company_id},
            ),
        )
        location_key = cast(
            int,
            _one(
                connection,
                """INSERT INTO analytics.dim_locations
                       (location_id, resolution_key, location_type, country_code, locality,
                        canonical_label, normalized_label, location_updated_at)
                   SELECT id, resolution_key, location_type, country_code, locality,
                          canonical_label, normalized_label, updated_at
                   FROM core.locations WHERE id=:location RETURNING location_key""",
                {"location": location_id},
            ),
        )
        occupation_key = cast(
            int,
            _one(
                connection,
                """INSERT INTO analytics.dim_occupations
                       (occupation_id, taxonomy_version_id, taxonomy_version, canonical_code,
                        canonical_name, normalized_name, parent_occupation_id, is_active,
                        occupation_updated_at)
                   SELECT o.id, o.taxonomy_version_id, v.version, o.canonical_code,
                          o.canonical_name, o.normalized_name, o.parent_id, o.is_active,
                          o.updated_at FROM taxonomy.occupations o
                   JOIN taxonomy.taxonomy_versions v ON v.id=o.taxonomy_version_id
                   WHERE o.id=:occupation RETURNING occupation_key""",
                {"occupation": occupation_id},
            ),
        )
        occupation_2_key = cast(
            int,
            _one(
                connection,
                """INSERT INTO analytics.dim_occupations
                       (occupation_id, taxonomy_version_id, taxonomy_version, canonical_code,
                        canonical_name, normalized_name, parent_occupation_id, is_active,
                        occupation_updated_at)
                   SELECT o.id, o.taxonomy_version_id, v.version, o.canonical_code,
                          o.canonical_name, o.normalized_name, o.parent_id, o.is_active,
                          o.updated_at FROM taxonomy.occupations o
                   JOIN taxonomy.taxonomy_versions v ON v.id=o.taxonomy_version_id
                   WHERE o.id=:occupation RETURNING occupation_key""",
                {"occupation": occupation_2_id},
            ),
        )
        skill_key = cast(
            int,
            _one(
                connection,
                """INSERT INTO analytics.dim_skills
                       (skill_id, taxonomy_version_id, taxonomy_version, canonical_code,
                        canonical_name, normalized_name, skill_type, parent_skill_id,
                        is_active, skill_updated_at)
                   SELECT s.id, s.taxonomy_version_id, v.version, s.canonical_code,
                          s.canonical_name, s.normalized_name, s.skill_type, s.parent_id,
                          s.is_active, s.updated_at FROM taxonomy.skills s
                   JOIN taxonomy.taxonomy_versions v ON v.id=s.taxonomy_version_id
                   WHERE s.id=:skill RETURNING skill_key""",
                {"skill": skill_id},
            ),
        )
        fact_id = cast(
            int,
            _one(
                connection,
                """INSERT INTO analytics.fact_job_observations
                       (observation_id, job_posting_id, source_key, company_key,
                        observed_date_key, posted_date_key, observation_reason, status,
                        employment_type_code, seniority_level_code, work_mode,
                        salary_disclosed, skill_count, occupation_count, location_count,
                        is_first_observation, canonical_hash, normalization_version,
                        refresh_run_id)
                   VALUES (:observation, :job, :source_key, :company_key, 20260115, 20260114,
                           'first_seen', 'active', 'full_time', 'mid', 'remote', true,
                           2, 2, 1, true, :hash, 'analytics.v1', :refresh) RETURNING
                           job_observation_fact_id""",
                {
                    "observation": observation_id,
                    "job": job_id,
                    "source_key": source_key,
                    "company_key": company_key,
                    "hash": "b" * 64,
                    "refresh": refresh_id,
                },
            ),
        )
    return locals()


def test_schema_dates_and_unknown_dimensions(engine: sa.Engine) -> None:
    assert set(sa.inspect(engine).get_table_names(schema="analytics")) == ANALYTICS_TABLES
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == (
            "20260727_0005"
        )
        assert connection.execute(
            sa.text("SELECT min(calendar_date), max(calendar_date) FROM analytics.dim_dates")
        ).one() == (date(2020, 1, 1), date(2035, 12, 31))
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM analytics.dim_dates WHERE calendar_date='2024-02-29'")
            )
            == 1
        )
        assert (
            connection.execute(
                sa.text(
                    """SELECT location_key, location_id, canonical_label
                   FROM analytics.dim_locations WHERE location_key=-1"""
                )
            ).one()
            == (-1, None, "Unknown location")
        )
        assert (
            connection.execute(
                sa.text(
                    """SELECT occupation_key, occupation_id, taxonomy_version_id, canonical_code
                   FROM analytics.dim_occupations WHERE occupation_key=-1"""
                )
            ).one()
            == (-1, None, None, "unknown")
        )


def test_refresh_constraints_and_type_one_dimension(
    engine: sa.Engine, catalog: dict[str, object]
) -> None:
    _reject(
        engine,
        """INSERT INTO analytics.refresh_runs
               (run_type, calculation_version, window_start_date, window_end_date)
           VALUES ('test', 'v1', '2026-02-01', '2026-01-01')""",
        {},
    )
    _reject(
        engine,
        """INSERT INTO analytics.refresh_runs
               (run_type, status, calculation_version)
           VALUES ('test', 'succeeded', 'v1')""",
        {},
    )
    with engine.begin() as connection:
        key_before = catalog["company_key"]
        connection.execute(
            sa.text(
                """UPDATE analytics.dim_companies
                   SET canonical_name='EXAMPLE_NOT_REAL_DATA Company Renamed'
                   WHERE company_key=:key"""
            ),
            {"key": key_before},
        )
        assert (
            connection.execute(
                sa.text(
                    """SELECT company_key, canonical_name FROM analytics.dim_companies
                   WHERE company_key=:key"""
                ),
                {"key": key_before},
            ).one()
            == (key_before, "EXAMPLE_NOT_REAL_DATA Company Renamed")
        )
    _reject(
        engine,
        """INSERT INTO analytics.dim_sources
               (source_id, slug, display_name, source_type, status, is_enabled,
                source_updated_at)
           SELECT source_id, 'another-analytics-slug', display_name, source_type,
                  status, is_enabled, source_updated_at
           FROM analytics.dim_sources WHERE source_key=:source_key""",
        {"source_key": catalog["source_key"]},
    )


def test_fact_idempotency_null_salary_and_bridges(
    engine: sa.Engine, catalog: dict[str, object]
) -> None:
    _reject(
        engine,
        """INSERT INTO analytics.fact_job_observations
               (observation_id, job_posting_id, source_key, observed_date_key,
                observation_reason, status, is_first_observation, canonical_hash,
                normalization_version, refresh_run_id)
           VALUES (:observation, :job, :source_key, 20260115, 'first_seen', 'active',
                   true, :hash, 'analytics.v1', :refresh)""",
        {
            "observation": catalog["observation_id"],
            "job": catalog["job_id"],
            "source_key": catalog["source_key"],
            "hash": "b" * 64,
            "refresh": catalog["refresh_id"],
        },
    )
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """INSERT INTO analytics.fact_salary_observations
                       (observation_salary_id, observation_id, job_observation_fact_id,
                        observed_date_key, source_key, company_key, amount_min, amount_max,
                        currency, period, compensation_type, tax_basis, is_disclosed,
                        is_negotiable, is_estimated, normalized_monthly_min,
                        normalized_monthly_max, refresh_run_id)
                   VALUES (:salary, :observation, :fact, 20260115, :source, :company,
                           1000, 2000, 'USD', 'month', 'base_salary', 'gross', true,
                           false, false, 1000, 2000, :refresh),
                          (:null_salary, :observation, :fact, 20260115, :source, :company,
                           NULL, NULL, NULL, NULL, 'base_salary', 'unknown', false,
                           false, false, NULL, NULL, :refresh)"""
            ),
            {
                "salary": catalog["salary_id"],
                "null_salary": catalog["null_salary_id"],
                "observation": catalog["observation_id"],
                "fact": catalog["fact_id"],
                "source": catalog["source_key"],
                "company": catalog["company_key"],
                "refresh": catalog["refresh_id"],
            },
        )
        assert (
            connection.execute(
                sa.text(
                    """SELECT amount_min, amount_max, currency, period
                   FROM analytics.fact_salary_observations
                   WHERE observation_salary_id=:salary"""
                ),
                {"salary": catalog["null_salary_id"]},
            ).one()
            == (None, None, None, None)
        )
        connection.execute(
            sa.text(
                """INSERT INTO analytics.bridge_job_observation_locations
                       (job_observation_fact_id, observation_location_id, location_key,
                        relationship_type, is_primary, is_remote, remote_scope,
                        refresh_run_id)
                   VALUES (:fact, :history_id, :dimension, 'workplace', true, true,
                           'vietnam', :refresh)"""
            ),
            {
                "fact": catalog["fact_id"],
                "history_id": catalog["observation_location_id"],
                "dimension": catalog["location_key"],
                "refresh": catalog["refresh_id"],
            },
        )
        connection.execute(
            sa.text(
                """INSERT INTO analytics.bridge_job_observation_occupations
                       (job_observation_fact_id, observation_occupation_id, occupation_key,
                        is_primary, refresh_run_id)
                   VALUES (:fact, :history_id, :dimension, true, :refresh)"""
            ),
            {
                "fact": catalog["fact_id"],
                "history_id": catalog["observation_occupation_id"],
                "dimension": catalog["occupation_key"],
                "refresh": catalog["refresh_id"],
            },
        )
        for history_id, requirement in zip(
            cast(list[int], catalog["skill_rows"]), ("required", "preferred"), strict=True
        ):
            connection.execute(
                sa.text(
                    """INSERT INTO analytics.bridge_job_observation_skills
                           (job_observation_fact_id, observation_skill_id, skill_key,
                            requirement_type, refresh_run_id)
                       VALUES (:fact, :history_id, :dimension, :requirement, :refresh)"""
                ),
                {
                    "fact": catalog["fact_id"],
                    "history_id": history_id,
                    "dimension": catalog["skill_key"],
                    "requirement": requirement,
                    "refresh": catalog["refresh_id"],
                },
            )
    _reject(
        engine,
        """INSERT INTO analytics.fact_salary_observations
               (observation_salary_id, observation_id, job_observation_fact_id,
                observed_date_key, source_key, compensation_type, tax_basis,
                is_disclosed, is_negotiable, is_estimated, refresh_run_id)
           VALUES (:salary, :observation, :fact, 20260115, :source, 'base_salary',
                   'unknown', false, false, false, :refresh)""",
        {
            "salary": catalog["salary_id"],
            "observation": catalog["observation_id"],
            "fact": catalog["fact_id"],
            "source": catalog["source_key"],
            "refresh": catalog["refresh_id"],
        },
    )
    _reject(
        engine,
        """INSERT INTO analytics.bridge_job_observation_occupations
               (job_observation_fact_id, observation_occupation_id, occupation_key,
                is_primary, refresh_run_id)
           VALUES (:fact, :history_id, :dimension, true, :refresh)""",
        {
            "fact": catalog["fact_id"],
            "history_id": catalog["observation_occupation_2_id"],
            "dimension": catalog["occupation_2_key"],
            "refresh": catalog["refresh_id"],
        },
    )


def test_daily_grains_are_separate_rebuildable_and_checked(
    engine: sa.Engine, catalog: dict[str, object]
) -> None:
    shared = {
        "date": "2026-01-15",
        "source": catalog["source_key"],
        "company": catalog["company_key"],
        "location": catalog["location_key"],
        "occupation": catalog["occupation_key"],
        "skill": catalog["skill_key"],
        "refresh": catalog["refresh_id"],
    }
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """INSERT INTO analytics.daily_market_metrics
                       (metric_date, source_key, employment_type_code,
                        seniority_level_code, work_mode, active_posting_count,
                        refresh_run_id, calculation_version)
                   VALUES (:date, :source, 'full_time', 'mid', 'remote', 1,
                           :refresh, 'analytics-test.v1'),
                          (:date, :source, 'full_time', 'mid', 'onsite', 2,
                           :refresh, 'analytics-test.v1')"""
            ),
            shared,
        )
        connection.execute(
            sa.text(
                """INSERT INTO analytics.daily_company_hiring
                       (metric_date, company_key, source_key, active_posting_count,
                        refresh_run_id, calculation_version)
                   VALUES (:date, :company, :source, 1, :refresh, 'analytics-test.v1')"""
            ),
            shared,
        )
        connection.execute(
            sa.text(
                """INSERT INTO analytics.daily_location_demand
                       (metric_date, location_key, source_key, work_mode,
                        active_posting_count, refresh_run_id, calculation_version)
                   VALUES (:date, :location, :source, 'remote', 1, :refresh,
                           'analytics-test.v1'),
                          (:date, :location, :source, 'hybrid', 1, :refresh,
                           'analytics-test.v1')"""
            ),
            shared,
        )
        connection.execute(
            sa.text(
                """INSERT INTO analytics.daily_occupation_demand
                       (metric_date, occupation_key, source_key, active_posting_count,
                        refresh_run_id, calculation_version)
                   VALUES (:date, :occupation, :source, 1, :refresh, 'analytics-test.v1')"""
            ),
            shared,
        )
        connection.execute(
            sa.text(
                """INSERT INTO analytics.daily_skill_demand
                       (metric_date, skill_key, source_key, requirement_type,
                        active_posting_count, refresh_run_id, calculation_version)
                   VALUES (:date, :skill, :source, 'required', 1, :refresh,
                           'analytics-test.v1'),
                          (:date, :skill, :source, 'preferred', 1, :refresh,
                           'analytics-test.v1')"""
            ),
            shared,
        )
        connection.execute(
            sa.text(
                """INSERT INTO analytics.daily_salary_metrics
                       (metric_date, source_key, occupation_key, location_key,
                        currency, period, tax_basis, disclosed_salary_count,
                        amount_min_average, refresh_run_id, calculation_version)
                   VALUES (:date, :source, :occupation, :location, 'USD', 'month',
                           'gross', 1, 1000, :refresh, 'analytics-test.v1'),
                          (:date, :source, :occupation, :location, 'VND', 'month',
                           'gross', 1, 25000000, :refresh, 'analytics-test.v1'),
                          (:date, :source, :occupation, :location, 'USD', 'year',
                           'gross', 1, 12000, :refresh, 'analytics-test.v1'),
                          (:date, :source, :occupation, :location, 'USD', 'month',
                           'net', 1, 900, :refresh, 'analytics-test.v1')"""
            ),
            shared,
        )
        connection.execute(
            sa.text(
                """INSERT INTO analytics.daily_market_metrics
                       (metric_date, source_key, employment_type_code,
                        seniority_level_code, work_mode, active_posting_count,
                        refresh_run_id, calculation_version)
                   VALUES (:date, :source, 'full_time', 'mid', 'remote', 3,
                           :refresh, 'analytics-test.v2')
                   ON CONFLICT (metric_date, source_key, employment_type_code,
                                seniority_level_code, work_mode)
                   DO UPDATE SET active_posting_count=excluded.active_posting_count,
                                 refresh_run_id=excluded.refresh_run_id,
                                 calculation_version=excluded.calculation_version,
                                 calculated_at=now()"""
            ),
            shared,
        )
        assert (
            connection.execute(
                sa.text(
                    """SELECT active_posting_count, calculation_version
                   FROM analytics.daily_market_metrics
                   WHERE metric_date=:date AND source_key=:source
                     AND employment_type_code='full_time' AND seniority_level_code='mid'
                     AND work_mode='remote'"""
                ),
                shared,
            ).one()
            == (3, "analytics-test.v2")
        )
        assert (
            connection.scalar(
                sa.text(
                    """SELECT count(*) FROM analytics.daily_salary_metrics
                   WHERE metric_date=:date AND source_key=:source"""
                ),
                shared,
            )
            == 4
        )
    for table, columns, values in (
        (
            "daily_market_metrics",
            "employment_type_code, seniority_level_code, work_mode, active_posting_count",
            "'full_time', 'mid', 'remote', 1",
        ),
        ("daily_company_hiring", "company_key", ":company"),
        ("daily_location_demand", "location_key, work_mode", ":location, 'remote'"),
        ("daily_occupation_demand", "occupation_key", ":occupation"),
        ("daily_skill_demand", "skill_key, requirement_type", ":skill, 'required'"),
        (
            "daily_salary_metrics",
            "occupation_key, location_key, currency, period, tax_basis, disclosed_salary_count",
            ":occupation, :location, 'USD', 'month', 'gross', 1",
        ),
    ):
        _reject(
            engine,
            f"""INSERT INTO analytics.{table}
                    (metric_date, source_key, {columns}, refresh_run_id, calculation_version)
                VALUES (:date, :source, {values}, :refresh, 'duplicate')""",
            shared,
        )
    _reject(
        engine,
        """INSERT INTO analytics.daily_company_hiring
               (metric_date, company_key, source_key, active_posting_count,
                refresh_run_id, calculation_version)
           VALUES ('2026-01-16', :company, :source, -1, :refresh, 'invalid')""",
        shared,
    )
    _reject(
        engine,
        """INSERT INTO analytics.daily_salary_metrics
               (metric_date, source_key, occupation_key, location_key, currency, period,
                tax_basis, disclosed_salary_count, refresh_run_id, calculation_version)
           VALUES ('2026-01-16', :source, -1, -1, 'USD', 'month', 'gross', 0,
                   :refresh, 'invalid')""",
        shared,
    )


def test_zz_downgrade_removes_only_analytics_and_reupgrade(engine: sa.Engine) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    engine.dispose()
    command.downgrade(config, "20260727_0004")
    check_engine = sa.create_engine(DATABASE_URL)
    try:
        inspector = sa.inspect(check_engine)
        assert "analytics" not in inspector.get_schema_names()
        assert "job_observations" in inspector.get_table_names(schema="history")
        assert "job_postings" in inspector.get_table_names(schema="core")
        assert "sources" in inspector.get_table_names(schema="ingestion")
    finally:
        check_engine.dispose()
    command.upgrade(config, "head")
    reupgraded = sa.create_engine(DATABASE_URL)
    try:
        assert set(sa.inspect(reupgraded).get_table_names(schema="analytics")) == (ANALYTICS_TABLES)
        with reupgraded.connect() as connection:
            assert (
                connection.scalar(
                    sa.text("SELECT count(*) FROM analytics.dim_locations WHERE location_key=-1")
                )
                == 1
            )
            assert (
                connection.scalar(
                    sa.text(
                        "SELECT count(*) FROM analytics.dim_occupations WHERE occupation_key=-1"
                    )
                )
                == 1
            )
    finally:
        reupgraded.dispose()
