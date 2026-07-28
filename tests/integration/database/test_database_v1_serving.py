"""PostgreSQL integration tests for Database V1 Migration 006."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.exc import DBAPIError, ProgrammingError

from alembic import command

DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="Database V1 serving integration tests require PostgreSQL",
)

SERVING_TABLES = {"refresh_runs", "job_search_documents", "job_search_salary_offers"}
SERVING_VIEWS = {
    "v_current_job_cards",
    "v_market_overview_daily",
    "v_company_hiring_daily",
    "v_location_demand_daily",
    "v_occupation_demand_daily",
    "v_skill_demand_daily",
    "v_salary_metrics_daily",
}
API_FUNCTIONS = {
    "search_jobs_v1",
    "get_job_v1",
    "market_overview_v1",
    "company_hiring_v1",
    "location_demand_v1",
    "occupation_demand_v1",
    "skill_demand_v1",
    "salary_metrics_v1",
}
API_OUTPUTS = {
    "search_jobs_v1": (
        "job_posting_id:uuid",
        "observation_id:bigint",
        "title:text",
        "company_id:uuid",
        "company_name:text",
        "source_id:uuid",
        "source_slug:text",
        "source_display_name:text",
        "source_url:text",
        "canonical_url:text",
        "status:text",
        "posted_at:timestamp with time zone",
        "expires_at:timestamp with time zone",
        "first_seen_at:timestamp with time zone",
        "last_seen_at:timestamp with time zone",
        "employment_type_code:text",
        "seniority_level_code:text",
        "work_mode:text",
        "location_labels:text[]",
        "occupation_names:text[]",
        "skill_names:text[]",
        "salary_disclosed:boolean",
        "salary_offers_json:jsonb",
        "rank_score:real",
        "total_count:bigint",
    ),
    "get_job_v1": (
        "job_posting_id:uuid",
        "observation_id:bigint",
        "source_id:uuid",
        "source_slug:text",
        "source_display_name:text",
        "source_job_id:text",
        "company_id:uuid",
        "source_url:text",
        "canonical_url:text",
        "title:text",
        "title_normalized:text",
        "company_name:text",
        "description_excerpt:text",
        "employment_type_code:text",
        "seniority_level_code:text",
        "work_mode:text",
        "status:text",
        "posted_at:timestamp with time zone",
        "expires_at:timestamp with time zone",
        "first_seen_at:timestamp with time zone",
        "last_seen_at:timestamp with time zone",
        "locations_json:jsonb",
        "occupations_json:jsonb",
        "skills_json:jsonb",
        "salary_offers_json:jsonb",
        "document_version:text",
        "updated_at:timestamp with time zone",
    ),
    "market_overview_v1": (
        "metric_date:date",
        "active_posting_count:bigint",
        "new_posting_count:bigint",
        "closed_posting_count:bigint",
        "expired_posting_count:bigint",
        "removed_posting_count:bigint",
        "reactivated_posting_count:bigint",
        "content_changed_count:bigint",
        "salary_disclosed_count:bigint",
        "remote_posting_count:bigint",
    ),
    "company_hiring_v1": (
        "metric_date:date",
        "source_id:uuid",
        "source_slug:text",
        "source_display_name:text",
        "company_id:uuid",
        "company_name:text",
        "company_type:text",
        "active_posting_count:bigint",
        "new_posting_count:bigint",
        "closed_posting_count:bigint",
        "unique_occupation_count:bigint",
        "unique_skill_count:bigint",
        "salary_disclosed_count:bigint",
        "remote_posting_count:bigint",
        "calculation_version:text",
        "calculated_at:timestamp with time zone",
    ),
    "location_demand_v1": (
        "metric_date:date",
        "source_id:uuid",
        "source_slug:text",
        "location_id:uuid",
        "location_label:text",
        "country_code:text",
        "admin_level_1:text",
        "admin_level_2:text",
        "locality:text",
        "work_mode:text",
        "active_posting_count:bigint",
        "new_posting_count:bigint",
        "closed_posting_count:bigint",
        "salary_disclosed_count:bigint",
        "calculation_version:text",
        "calculated_at:timestamp with time zone",
    ),
    "occupation_demand_v1": (
        "metric_date:date",
        "source_id:uuid",
        "source_slug:text",
        "occupation_id:uuid",
        "occupation_name:text",
        "occupation_code:text",
        "taxonomy_version:text",
        "active_posting_count:bigint",
        "new_posting_count:bigint",
        "closed_posting_count:bigint",
        "salary_disclosed_count:bigint",
        "remote_posting_count:bigint",
        "calculation_version:text",
        "calculated_at:timestamp with time zone",
    ),
    "skill_demand_v1": (
        "metric_date:date",
        "source_id:uuid",
        "source_slug:text",
        "skill_id:uuid",
        "skill_name:text",
        "skill_code:text",
        "skill_type:text",
        "taxonomy_version:text",
        "requirement_type:text",
        "active_posting_count:bigint",
        "new_posting_count:bigint",
        "closed_posting_count:bigint",
        "company_count:bigint",
        "occupation_count:bigint",
        "calculation_version:text",
        "calculated_at:timestamp with time zone",
    ),
    "salary_metrics_v1": (
        "metric_date:date",
        "source_id:uuid",
        "source_slug:text",
        "occupation_id:uuid",
        "occupation_name:text",
        "location_id:uuid",
        "location_label:text",
        "currency:text",
        "period:text",
        "tax_basis:text",
        "disclosed_salary_count:bigint",
        "estimated_salary_count:bigint",
        "negotiable_salary_count:bigint",
        "amount_min_average:numeric",
        "amount_max_average:numeric",
        "amount_exact_average:numeric",
        "normalized_monthly_min_average:numeric",
        "normalized_monthly_max_average:numeric",
        "normalized_annual_min_average:numeric",
        "normalized_annual_max_average:numeric",
        "normalized_monthly_min_median:numeric",
        "normalized_monthly_max_median:numeric",
        "normalized_annual_min_median:numeric",
        "normalized_annual_max_median:numeric",
        "calculation_version:text",
        "calculated_at:timestamp with time zone",
    ),
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


def _reject(engine: sa.Engine, sql: str, values: dict[str, object]) -> DBAPIError:
    with pytest.raises(DBAPIError) as error, engine.begin() as connection:
        connection.execute(sa.text(sql), values)
    return error.value


@pytest.fixture(scope="module")
def catalog(engine: sa.Engine) -> dict[str, object]:
    with engine.begin() as connection:
        source = _one(
            connection,
            """INSERT INTO ingestion.sources
                   (slug, display_name, base_url, status, is_enabled, country_code)
               VALUES ('serving-example-source', 'EXAMPLE_NOT_REAL_DATA Jobs',
                       'https://example.test', 'approved', true, 'VN') RETURNING id""",
            {},
        )
        parser = _one(
            connection,
            """INSERT INTO ingestion.parser_versions
                   (source_id, parser_name, version, schema_version)
               VALUES (:source, 'serving-example-parser', '1', 'direct.v1') RETURNING id""",
            {"source": source},
        )
        crawl = _one(
            connection,
            """INSERT INTO ingestion.crawl_runs (source_id, run_type, trigger_type)
               VALUES (:source, 'test', 'test') RETURNING id""",
            {"source": source},
        )
        task = _one(
            connection,
            """INSERT INTO ingestion.crawl_tasks
                   (crawl_run_id, source_id, task_type, requested_url)
               VALUES (:crawl, :source, 'detail_page',
                       'https://example.test/jobs/serving') RETURNING id""",
            {"crawl": crawl, "source": source},
        )
        fetch = _one(
            connection,
            """INSERT INTO ingestion.fetch_events
                   (crawl_run_id, crawl_task_id, source_id, requested_url, http_status,
                    robots_allowed, fetch_outcome, fetched_at)
               VALUES (:crawl, :task, :source, 'https://example.test/jobs/serving',
                       200, true, 'success', '2026-02-01T08:00:00Z') RETURNING id""",
            {"crawl": crawl, "task": task, "source": source},
        )
        extraction = _one(
            connection,
            """INSERT INTO ingestion.extraction_runs
                   (crawl_run_id, fetch_event_id, parser_version_id)
               VALUES (:crawl, :fetch, :parser) RETURNING id""",
            {"crawl": crawl, "fetch": fetch, "parser": parser},
        )
        record = _one(
            connection,
            """INSERT INTO ingestion.extracted_records
                   (extraction_run_id, source_id, source_job_id, fetch_event_id,
                    record_schema_version, direct_payload_json, direct_hash, extracted_at)
               VALUES (:extraction, :source, 'serving-job', :fetch, 'direct.v1',
                       '{}'::jsonb, :hash, '2026-02-01T08:01:00Z') RETURNING id""",
            {"extraction": extraction, "source": source, "fetch": fetch, "hash": "a" * 64},
        )
        location = _one(
            connection,
            """INSERT INTO core.locations
                   (resolution_key, location_type, country_code, locality,
                    canonical_label, normalized_label)
               VALUES ('serving-ho-chi-minh', 'city', 'VN', 'Ho Chi Minh City',
                       'EXAMPLE_NOT_REAL_DATA Ho Chi Minh City', 'ho chi minh city')
               RETURNING id""",
            {},
        )
        company = _one(
            connection,
            """INSERT INTO core.companies (canonical_name, normalized_name)
               VALUES ('EXAMPLE_NOT_REAL_DATA Cloud Company', 'example cloud company')
               RETURNING id""",
            {},
        )
        occupation_version = _one(
            connection,
            """INSERT INTO taxonomy.taxonomy_versions (taxonomy_type, version, name)
               VALUES ('occupation', 'SYNTHETIC_SERVING.v1',
                       'EXAMPLE_NOT_REAL_DATA occupations') RETURNING id""",
            {},
        )
        skill_version = _one(
            connection,
            """INSERT INTO taxonomy.taxonomy_versions (taxonomy_type, version, name)
               VALUES ('skill', 'SYNTHETIC_SERVING.v1',
                       'EXAMPLE_NOT_REAL_DATA skills') RETURNING id""",
            {},
        )
        occupation = _one(
            connection,
            """INSERT INTO taxonomy.occupations
                   (taxonomy_version_id, canonical_code, canonical_name, normalized_name)
               VALUES (:version, 'software-developer',
                       'EXAMPLE_NOT_REAL_DATA Software Developer', 'software developer')
               RETURNING id""",
            {"version": occupation_version},
        )
        skill = _one(
            connection,
            """INSERT INTO taxonomy.skills
                   (taxonomy_version_id, canonical_code, canonical_name, normalized_name)
               VALUES (:version, 'python', 'EXAMPLE_NOT_REAL_DATA Python', 'python')
               RETURNING id""",
            {"version": skill_version},
        )
        job = _one(
            connection,
            """INSERT INTO core.job_postings
                   (source_id, source_job_id, source_url, title_raw, company_id,
                    first_seen_at, last_seen_at, last_changed_at)
               VALUES (:source, 'serving-job', 'https://example.test/jobs/serving',
                       'EXAMPLE_NOT_REAL_DATA Python Platform Engineer', :company,
                       '2026-02-01T08:00:00Z', '2026-02-02T08:00:00Z',
                       '2026-02-01T08:00:00Z') RETURNING id""",
            {"source": source, "company": company},
        )
        observation = _one(
            connection,
            """INSERT INTO history.job_observations
                   (job_posting_id, source_id, source_job_id, extracted_record_id,
                    crawl_run_id, observation_reason, observed_at, canonical_hash,
                    status, source_url, title_raw, title_normalized, company_id,
                    company_name_raw, employment_type_code, seniority_level_code,
                    work_mode, posted_at, canonical_payload_json, normalization_version)
               VALUES (:job, :source, 'serving-job', :record, :crawl, 'first_seen',
                       '2026-02-01T08:00:00Z', :hash, 'active',
                       'https://example.test/jobs/serving',
                       'EXAMPLE_NOT_REAL_DATA Python Platform Engineer',
                       'python platform engineer', :company, 'Example Cloud',
                       'full_time', 'senior', 'hybrid', '2026-01-31T00:00:00Z',
                       '{}'::jsonb, 'serving.v1') RETURNING id""",
            {
                "job": job,
                "source": source,
                "record": record,
                "crawl": crawl,
                "hash": "b" * 64,
                "company": company,
            },
        )
        connection.execute(
            sa.text(
                """INSERT INTO history.observation_descriptions
                       (observation_id, description_text, content_hash)
                   VALUES (:observation,
                           'EXAMPLE_NOT_REAL_DATA distributed systems observability', :hash)"""
            ),
            {"observation": observation, "hash": "c" * 64},
        )
        connection.execute(
            sa.text(
                """INSERT INTO history.observation_locations
                       (observation_id, location_id, relationship_type, is_primary)
                   VALUES (:observation, :location, 'workplace', true)"""
            ),
            {"observation": observation, "location": location},
        )
        connection.execute(
            sa.text(
                """INSERT INTO history.observation_occupations
                       (observation_id, occupation_id, is_primary)
                   VALUES (:observation, :occupation, true)"""
            ),
            {"observation": observation, "occupation": occupation},
        )
        connection.execute(
            sa.text(
                """INSERT INTO history.observation_skills
                       (observation_id, skill_id, requirement_type)
                   VALUES (:observation, :skill, 'required')"""
            ),
            {"observation": observation, "skill": skill},
        )
        salary = _one(
            connection,
            """INSERT INTO history.observation_salaries
                   (observation_id, amount_min, amount_max, currency, period, tax_basis,
                    is_disclosed, normalized_monthly_min, normalized_monthly_max)
               VALUES (:observation, 2000, 3000, 'USD', 'month', 'gross', true,
                       2000, 3000) RETURNING id""",
            {"observation": observation},
        )
        connection.execute(
            sa.text(
                "UPDATE core.job_postings SET current_observation_id=:observation WHERE id=:job"
            ),
            {"observation": observation, "job": job},
        )
        serving_run = _one(
            connection,
            """INSERT INTO serving.refresh_runs
                   (run_type, status, document_version, source_id, started_at, finished_at)
               VALUES ('test', 'succeeded', 'serving-test.v1', :source,
                       '2026-02-02T09:00:00Z', '2026-02-02T09:01:00Z') RETURNING id""",
            {"source": source},
        )
        connection.execute(
            sa.text(
                """INSERT INTO serving.job_search_documents
                       (job_posting_id, observation_id, refresh_run_id, document_version)
                   VALUES (:job, :observation, :run, 'serving-test.v1')"""
            ),
            {"job": job, "observation": observation, "run": serving_run},
        )
    return locals()


def test_inventory_head_indexes_and_rls(engine: sa.Engine) -> None:
    inspector = sa.inspect(engine)
    assert set(inspector.get_table_names(schema="serving")) == SERVING_TABLES
    assert set(inspector.get_view_names(schema="serving")) == SERVING_VIEWS
    assert inspector.get_table_names(schema="api") == []
    assert inspector.get_view_names(schema="api") == []
    with engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == (
            "20260727_0006"
        )
        functions = set(
            connection.scalars(
                sa.text(
                    """SELECT routine_name FROM information_schema.routines
                       WHERE routine_schema='api' AND routine_name LIKE '%_v1'"""
                )
            )
        )
        assert functions == API_FUNCTIONS
        rls_tables = set(
            connection.scalars(
                sa.text(
                    """SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                       WHERE n.nspname='serving' AND c.relkind='r' AND c.relrowsecurity"""
                )
            )
        )
        assert rls_tables == SERVING_TABLES
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM pg_policies WHERE schemaname='serving'")
            )
            == 0
        )
        indexes = set(
            connection.scalars(
                sa.text("SELECT indexname FROM pg_indexes WHERE schemaname='serving'")
            )
        )
        assert {
            "ix_job_search_documents__search_vector",
            "ix_job_search_documents__skill_ids",
            "ix_job_search_documents__occupation_ids",
            "ix_job_search_documents__location_ids",
            "ix_search_salary_offers__range",
        } <= indexes
        triggers = set(
            connection.scalars(
                sa.text(
                    """SELECT tgname FROM pg_trigger
                       WHERE tgrelid IN (
                         'serving.job_search_documents'::regclass,
                         'serving.job_search_salary_offers'::regclass)
                         AND NOT tgisinternal"""
                )
            )
        )
        assert {
            "trg_job_search_documents__build",
            "trg_job_search_documents__rebuild_salaries",
            "trg_job_search_salary_offers__validate",
        } <= triggers


def test_builder_search_detail_and_filters(engine: sa.Engine, catalog: dict[str, object]) -> None:
    with engine.connect() as connection:
        document = connection.execute(
            sa.text(
                """SELECT title, company_name, description_excerpt, location_labels,
                          occupation_names, skill_names, salary_disclosed,
                          search_vector::text
                   FROM serving.job_search_documents WHERE job_posting_id=:job"""
            ),
            {"job": catalog["job"]},
        ).one()
        assert "Python Platform Engineer" in document.title
        assert document.company_name == "EXAMPLE_NOT_REAL_DATA Cloud Company"
        assert "distributed systems" in document.description_excerpt
        assert len(document.location_labels) == 1
        assert len(document.occupation_names) == 1
        assert len(document.skill_names) == 1
        assert document.salary_disclosed is True
        assert "python" in document.search_vector
        result = (
            connection.execute(sa.text("SELECT * FROM api.search_jobs_v1(p_query=>'Python')"))
            .mappings()
            .one()
        )
        assert result["job_posting_id"] == catalog["job"]
        assert result["rank_score"] > 0
        assert result["total_count"] == 1
        assert len(result["salary_offers_json"]) == 1
        assert (
            connection.scalar(
                sa.text(
                    """SELECT count(*) FROM api.search_jobs_v1(
                       p_skill_ids=>ARRAY[:skill]::uuid[], p_location_ids=>ARRAY[:location]::uuid[],
                       p_salary_currency=>'USD', p_salary_period=>'month',
                       p_salary_tax_basis=>'gross', p_salary_min=>2500, p_salary_max=>2500)"""
                ),
                {"skill": catalog["skill"], "location": catalog["location"]},
            )
            == 1
        )
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM api.search_jobs_v1(p_query=>'\"Python Platform\"')")
            )
            == 1
        )
        detail = (
            connection.execute(
                sa.text("SELECT * FROM api.get_job_v1(:job)"), {"job": catalog["job"]}
            )
            .mappings()
            .one()
        )
        assert detail["job_posting_id"] == catalog["job"]
        assert len(detail["salary_offers_json"]) == 1
        assert "search_vector" not in detail
        assert "canonical_hash" not in detail
    for sql in (
        "SELECT * FROM api.search_jobs_v1(p_limit=>0)",
        "SELECT * FROM api.search_jobs_v1(p_limit=>NULL)",
        "SELECT * FROM api.search_jobs_v1(p_offset=>NULL)",
        "SELECT * FROM api.search_jobs_v1(p_sort=>NULL)",
        "SELECT * FROM api.search_jobs_v1(p_sort=>'invalid')",
        "SELECT * FROM api.search_jobs_v1(p_salary_min=>1)",
        "SELECT * FROM api.search_jobs_v1(p_source_ids=>ARRAY[NULL]::uuid[])",
        "SELECT * FROM api.search_jobs_v1(p_statuses=>ARRAY['active',NULL]::text[])",
        """SELECT * FROM api.search_jobs_v1(
               p_source_ids=>ARRAY(SELECT gen_random_uuid() FROM generate_series(1,101)))""",
    ):
        assert getattr(_reject(engine, sql, {}).orig, "sqlstate", None) == "22023"
    assert (
        getattr(
            _reject(
                engine,
                "SELECT * FROM api.search_jobs_v1(p_query=>:query)",
                {"query": "x" * 501},
            ).orig,
            "sqlstate",
            None,
        )
        == "22023"
    )
    for function_name in (
        "company_hiring_v1",
        "location_demand_v1",
        "occupation_demand_v1",
        "skill_demand_v1",
        "salary_metrics_v1",
    ):
        for parameter in ("p_limit", "p_offset"):
            error = _reject(
                engine,
                f"SELECT * FROM api.{function_name}({parameter}=>NULL)",
                {},
            )
            assert getattr(error.orig, "sqlstate", None) == "22023"


def test_api_output_contracts_are_explicit(engine: sa.Engine) -> None:
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                """SELECT p.proname, argument.arg_name,
                          pg_catalog.format_type(argument.arg_type, NULL) AS arg_type
                   FROM pg_proc AS p
                   JOIN pg_namespace AS namespace ON namespace.oid = p.pronamespace
                   CROSS JOIN LATERAL unnest(
                       p.proallargtypes, p.proargmodes, p.proargnames
                   ) WITH ORDINALITY AS argument(arg_type, arg_mode, arg_name, ordinality)
                   WHERE namespace.nspname = 'api' AND argument.arg_mode IN ('o', 't')
                   ORDER BY p.proname, argument.ordinality"""
            )
        ).all()
        actual: dict[str, list[str]] = {name: [] for name in API_FUNCTIONS}
        for function_name, column_name, column_type in rows:
            actual[function_name].append(f"{column_name}:{column_type}")
        assert {name: tuple(columns) for name, columns in actual.items()} == API_OUTPUTS

        private_composite_count = connection.scalar(
            sa.text(
                """SELECT count(*)
                   FROM pg_proc AS function
                   JOIN pg_namespace AS function_schema
                     ON function_schema.oid = function.pronamespace
                   JOIN pg_type AS return_type ON return_type.oid = function.prorettype
                   JOIN pg_class AS relation ON relation.oid = return_type.typrelid
                   JOIN pg_namespace AS relation_schema
                     ON relation_schema.oid = relation.relnamespace
                   WHERE function_schema.nspname='api'
                     AND relation_schema.nspname='serving'"""
            )
        )
        assert private_composite_count == 0
        defaults_rows = connection.execute(
            sa.text(
                """SELECT p.proname, pg_get_function_arguments(p.oid)
                       FROM pg_proc AS p JOIN pg_namespace AS n ON n.oid=p.pronamespace
                       WHERE n.nspname='api' AND p.proname IN
                         ('location_demand_v1','occupation_demand_v1','salary_metrics_v1')"""
            )
        ).all()
        defaults: dict[str, str] = {str(row[0]): str(row[1]) for row in defaults_rows}
        assert all("boolean DEFAULT false" in arguments for arguments in defaults.values())


def test_stale_hiding_and_concurrent_current_update(
    engine: sa.Engine, catalog: dict[str, object]
) -> None:
    with engine.begin() as connection:
        connection.execute(
            sa.text("UPDATE core.job_postings SET current_observation_id=NULL WHERE id=:job"),
            {"job": catalog["job"]},
        )
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM serving.v_current_job_cards WHERE job_posting_id=:job"
                ),
                {"job": catalog["job"]},
            )
            == 0
        )
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM api.get_job_v1(:job)"), {"job": catalog["job"]}
            )
            == 0
        )
        connection.execute(
            sa.text(
                "UPDATE core.job_postings SET current_observation_id=:observation WHERE id=:job"
            ),
            {"observation": catalog["observation"], "job": catalog["job"]},
        )
        connection.execute(
            sa.text(
                """UPDATE serving.job_search_documents SET observation_id=observation_id
                   WHERE job_posting_id=:job"""
            ),
            {"job": catalog["job"]},
        )

    lock_connection = engine.connect()
    lock_transaction = lock_connection.begin()
    try:
        lock_connection.execute(sa.text("SET LOCAL lock_timeout='5s'"))
        lock_connection.execute(
            sa.text(
                """UPDATE serving.job_search_documents SET observation_id=observation_id
                   WHERE job_posting_id=:job"""
            ),
            {"job": catalog["job"]},
        )
        started = Event()

        def advance_current() -> None:
            with engine.begin() as connection:
                connection.execute(sa.text("SET LOCAL lock_timeout='5s'"))
                connection.execute(sa.text("SET LOCAL statement_timeout='10s'"))
                started.set()
                connection.execute(
                    sa.text(
                        "UPDATE core.job_postings SET current_observation_id=NULL WHERE id=:job"
                    ),
                    {"job": catalog["job"]},
                )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(advance_current)
            assert started.wait(2)
            time.sleep(0.2)
            assert not future.done()
            lock_transaction.commit()
            future.result(timeout=10)
    finally:
        if lock_transaction.is_active:
            lock_transaction.rollback()
        lock_connection.close()
    with engine.begin() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM serving.v_current_job_cards WHERE job_posting_id=:job"
                ),
                {"job": catalog["job"]},
            )
            == 0
        )
        connection.execute(
            sa.text(
                "UPDATE core.job_postings SET current_observation_id=:observation WHERE id=:job"
            ),
            {"observation": catalog["observation"], "job": catalog["job"]},
        )


def test_search_relevance_and_blank_query_ordering(
    engine: sa.Engine, catalog: dict[str, object]
) -> None:
    jobs: list[object] = []
    with engine.begin() as connection:
        for index, posted_at in enumerate(("2026-02-03T00:00:00Z", "2026-02-04T00:00:00Z")):
            source_job_id = f"serving-tie-{index}"
            record = _one(
                connection,
                """INSERT INTO ingestion.extracted_records
                       (extraction_run_id, source_id, source_job_id, fetch_event_id,
                        record_schema_version, direct_payload_json, direct_hash, extracted_at)
                   VALUES (:extraction, :source, :source_job_id, :fetch, 'direct.v1',
                           '{}'::jsonb, :hash, :posted_at) RETURNING id""",
                {
                    "extraction": catalog["extraction"],
                    "source": catalog["source"],
                    "source_job_id": source_job_id,
                    "fetch": catalog["fetch"],
                    "hash": str(index + 7) * 64,
                    "posted_at": posted_at,
                },
            )
            job = _one(
                connection,
                """INSERT INTO core.job_postings
                       (source_id, source_job_id, source_url, title_raw,
                        first_seen_at, last_seen_at, last_changed_at)
                   VALUES (:source, :source_job_id, :url,
                           'EXAMPLE_NOT_REAL_DATA Tie Engineer', :posted_at,
                           :posted_at, :posted_at) RETURNING id""",
                {
                    "source": catalog["source"],
                    "source_job_id": source_job_id,
                    "url": f"https://example.test/jobs/{source_job_id}",
                    "posted_at": posted_at,
                },
            )
            observation = _one(
                connection,
                """INSERT INTO history.job_observations
                       (job_posting_id, source_id, source_job_id, extracted_record_id,
                        crawl_run_id, observation_reason, observed_at, canonical_hash,
                        status, source_url, title_raw, title_normalized, posted_at,
                        canonical_payload_json, normalization_version)
                   VALUES (:job, :source, :source_job_id, :record, :crawl, 'first_seen',
                           :posted_at, :hash, 'active', :url,
                           'EXAMPLE_NOT_REAL_DATA Tie Engineer', 'tie engineer', :posted_at,
                           '{}'::jsonb, 'serving.v1') RETURNING id""",
                {
                    "job": job,
                    "source": catalog["source"],
                    "source_job_id": source_job_id,
                    "record": record,
                    "crawl": catalog["crawl"],
                    "posted_at": posted_at,
                    "hash": str(index + 4) * 64,
                    "url": f"https://example.test/jobs/{source_job_id}",
                },
            )
            connection.execute(
                sa.text(
                    "UPDATE core.job_postings SET current_observation_id=:observation WHERE id=:job"
                ),
                {"observation": observation, "job": job},
            )
            connection.execute(
                sa.text(
                    """INSERT INTO serving.job_search_documents
                           (job_posting_id, observation_id, refresh_run_id, document_version)
                       VALUES (:job, :observation, :run, 'serving-test.v1')"""
                ),
                {"job": job, "observation": observation, "run": catalog["serving_run"]},
            )
            jobs.append(job)

    with engine.connect() as connection:
        relevance = list(
            connection.scalars(
                sa.text(
                    """SELECT job_posting_id FROM api.search_jobs_v1(
                           p_query=>'Tie Engineer', p_sort=>'relevance')"""
                )
            )
        )
        assert relevance == [jobs[1], jobs[0]]
        blank = list(
            connection.scalars(
                sa.text(
                    """SELECT job_posting_id FROM api.search_jobs_v1(
                           p_query=>'   ', p_sort=>'relevance', p_limit=>2)"""
                )
            )
        )
        assert blank == [jobs[1], jobs[0]]


def test_salary_projection_is_atomic_and_history_is_unchanged(
    engine: sa.Engine, catalog: dict[str, object]
) -> None:
    with engine.begin() as connection:
        observation_b = _one(
            connection,
            """INSERT INTO history.job_observations
                   (job_posting_id, source_id, source_job_id, extracted_record_id,
                    crawl_run_id, previous_observation_id, observation_reason, observed_at,
                    canonical_hash, status, source_url, title_raw, title_normalized,
                    company_id, company_name_raw, employment_type_code,
                    seniority_level_code, work_mode, posted_at, canonical_payload_json,
                    normalization_version)
               VALUES (:job, :source, 'serving-job', :record, :crawl, :previous,
                       'content_changed', '2026-02-05T08:00:00Z', :hash, 'active',
                       'https://example.test/jobs/serving',
                       'EXAMPLE_NOT_REAL_DATA Python Platform Engineer II',
                       'python platform engineer ii', :company, 'Example Cloud',
                       'full_time', 'senior', 'hybrid', '2026-01-31T00:00:00Z',
                       '{}'::jsonb, 'serving.v2') RETURNING id""",
            {
                "job": catalog["job"],
                "source": catalog["source"],
                "record": catalog["record"],
                "crawl": catalog["crawl"],
                "previous": catalog["observation"],
                "hash": "e" * 64,
                "company": catalog["company"],
            },
        )
        salary_b1 = _one(
            connection,
            """INSERT INTO history.observation_salaries
                   (observation_id, amount_min, amount_max, currency, period, tax_basis,
                    is_disclosed, normalized_monthly_min, normalized_monthly_max)
               VALUES (:observation, 4000, 5000, 'USD', 'month', 'gross', true,
                       4000, 5000) RETURNING id""",
            {"observation": observation_b},
        )
        salary_b2 = _one(
            connection,
            """INSERT INTO history.observation_salaries
                   (observation_id, offer_index, amount_exact, currency, period, tax_basis,
                    compensation_type, is_disclosed)
               VALUES (:observation, 1, 800, 'USD', 'month', 'gross', 'bonus', true)
               RETURNING id""",
            {"observation": observation_b},
        )
        run_b = _one(
            connection,
            """INSERT INTO serving.refresh_runs
                   (run_type, status, document_version, source_id, started_at, finished_at)
               VALUES ('test', 'succeeded', 'serving-test.v1', :source, now(), now())
               RETURNING id""",
            {"source": catalog["source"]},
        )
        connection.execute(
            sa.text(
                "UPDATE core.job_postings SET current_observation_id=:observation WHERE id=:job"
            ),
            {"observation": observation_b, "job": catalog["job"]},
        )
        connection.execute(
            sa.text(
                """UPDATE serving.job_search_documents
                   SET observation_id=:observation, refresh_run_id=:run
                   WHERE job_posting_id=:job"""
            ),
            {"observation": observation_b, "run": run_b, "job": catalog["job"]},
        )

    with engine.connect() as connection:
        salary_rows = [
            (row[0], row[1])
            for row in connection.execute(
                sa.text(
                    """SELECT observation_salary_id, refresh_run_id
                   FROM serving.job_search_salary_offers
                   WHERE job_posting_id=:job ORDER BY observation_salary_id"""
                ),
                {"job": catalog["job"]},
            ).all()
        ]
        assert salary_rows == [(salary_b1, run_b), (salary_b2, run_b)]
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM history.observation_salaries WHERE id=:salary"),
                {"salary": catalog["salary"]},
            )
            == 1
        )

    with engine.begin() as connection:
        lineage_run = _one(
            connection,
            """INSERT INTO serving.refresh_runs
                   (run_type, status, document_version, source_id, started_at, finished_at)
               VALUES ('test', 'succeeded', 'serving-test.v1', :source, now(), now())
               RETURNING id""",
            {"source": catalog["source"]},
        )
        connection.execute(
            sa.text(
                """UPDATE serving.job_search_documents SET refresh_run_id=:run
                   WHERE job_posting_id=:job"""
            ),
            {"run": lineage_run, "job": catalog["job"]},
        )
    with engine.connect() as connection:
        assert (
            set(
                connection.scalars(
                    sa.text(
                        """SELECT refresh_run_id FROM serving.job_search_salary_offers
                       WHERE job_posting_id=:job"""
                    ),
                    {"job": catalog["job"]},
                )
            )
            == {lineage_run}
        )

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE core.job_postings SET current_observation_id=:observation WHERE id=:job"
            ),
            {"observation": catalog["observation"], "job": catalog["job"]},
        )
        connection.execute(
            sa.text(
                """UPDATE serving.job_search_documents
                   SET observation_id=:observation, refresh_run_id=:run,
                       document_version='serving-test.v1'
                   WHERE job_posting_id=:job"""
            ),
            {
                "observation": catalog["observation"],
                "run": catalog["serving_run"],
                "job": catalog["job"],
            },
        )
    with engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    """SELECT observation_salary_id FROM serving.job_search_salary_offers
                   WHERE job_posting_id=:job"""
                ),
                {"job": catalog["job"]},
            )
            == catalog["salary"]
        )

    for statement in ("INSERT", "UPDATE", "DELETE"):
        connection = engine.connect()
        transaction = connection.begin()
        try:
            connection.execute(sa.text("SET ROLE service_role"))
            if statement == "INSERT":
                sql = "INSERT INTO serving.job_search_salary_offers DEFAULT VALUES"
            elif statement == "UPDATE":
                sql = "UPDATE serving.job_search_salary_offers SET updated_at=now()"
            else:
                sql = "DELETE FROM serving.job_search_salary_offers"
            with pytest.raises(ProgrammingError) as error:
                connection.execute(sa.text(sql))
            assert getattr(error.value.orig, "sqlstate", None) == "42501"
        finally:
            transaction.rollback()
            connection.close()

    connection = engine.connect()
    transaction = connection.begin()
    try:
        connection.execute(
            sa.text("DELETE FROM serving.job_search_documents WHERE job_posting_id=:job"),
            {"job": catalog["job"]},
        )
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM history.observation_salaries WHERE id=:salary"),
                {"salary": catalog["salary"]},
            )
            == 1
        )
    finally:
        transaction.rollback()
        connection.close()


def test_refresh_run_lineage_is_concurrency_safe(
    engine: sa.Engine, catalog: dict[str, object]
) -> None:
    document_connection = engine.connect()
    document_transaction = document_connection.begin()
    try:
        document_connection.execute(sa.text("SET LOCAL lock_timeout='5s'"))
        document_connection.execute(
            sa.text(
                """UPDATE serving.job_search_documents SET observation_id=observation_id
                   WHERE job_posting_id=:job"""
            ),
            {"job": catalog["job"]},
        )
        started = Event()

        def mutate_referenced_run() -> str | None:
            try:
                with engine.begin() as connection:
                    connection.execute(sa.text("SET LOCAL lock_timeout='5s'"))
                    connection.execute(sa.text("SET LOCAL statement_timeout='10s'"))
                    started.set()
                    connection.execute(
                        sa.text(
                            """UPDATE serving.refresh_runs
                               SET document_version='forbidden.v2' WHERE id=:run"""
                        ),
                        {"run": catalog["serving_run"]},
                    )
            except DBAPIError as error:
                sqlstate = getattr(error.orig, "sqlstate", None)
                return sqlstate if isinstance(sqlstate, str) else None
            return None

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(mutate_referenced_run)
            assert started.wait(2)
            time.sleep(0.2)
            assert not future.done()
            document_transaction.commit()
            assert future.result(timeout=10) == "23514"
    finally:
        if document_transaction.is_active:
            document_transaction.rollback()
        document_connection.close()

    with engine.begin() as connection:
        pending_run = _one(
            connection,
            """INSERT INTO serving.refresh_runs
                   (run_type, status, document_version, source_id, started_at, finished_at)
               VALUES ('test', 'succeeded', 'before.v1', :source, now(), now()) RETURNING id""",
            {"source": catalog["source"]},
        )

    refresh_connection = engine.connect()
    refresh_transaction = refresh_connection.begin()
    try:
        refresh_connection.execute(sa.text("SET LOCAL lock_timeout='5s'"))
        refresh_connection.execute(
            sa.text("UPDATE serving.refresh_runs SET document_version='after.v2' WHERE id=:run"),
            {"run": pending_run},
        )
        started = Event()

        def attach_final_run() -> None:
            with engine.begin() as connection:
                connection.execute(sa.text("SET LOCAL lock_timeout='5s'"))
                connection.execute(sa.text("SET LOCAL statement_timeout='10s'"))
                started.set()
                connection.execute(
                    sa.text(
                        """UPDATE serving.job_search_documents
                           SET refresh_run_id=:run, document_version='after.v2'
                           WHERE job_posting_id=:job"""
                    ),
                    {"run": pending_run, "job": catalog["job"]},
                )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(attach_final_run)
            assert started.wait(2)
            time.sleep(0.2)
            assert not future.done()
            refresh_transaction.commit()
            future.result(timeout=10)
    finally:
        if refresh_transaction.is_active:
            refresh_transaction.rollback()
        refresh_connection.close()

    with engine.begin() as connection:
        assert (
            connection.scalar(
                sa.text(
                    """SELECT refresh_run_id FROM serving.job_search_documents
                       WHERE job_posting_id=:job"""
                ),
                {"job": catalog["job"]},
            )
            == pending_run
        )
        assert (
            set(
                connection.scalars(
                    sa.text(
                        """SELECT refresh_run_id FROM serving.job_search_salary_offers
                       WHERE job_posting_id=:job"""
                    ),
                    {"job": catalog["job"]},
                )
            )
            == {pending_run}
        )
        connection.execute(
            sa.text(
                """UPDATE serving.job_search_documents
                   SET refresh_run_id=:run, document_version='serving-test.v1'
                   WHERE job_posting_id=:job"""
            ),
            {"run": catalog["serving_run"], "job": catalog["job"]},
        )


def test_dashboard_functions_and_validation(engine: sa.Engine, catalog: dict[str, object]) -> None:
    with engine.begin() as connection:
        analytics_run = _one(
            connection,
            """INSERT INTO analytics.refresh_runs
                   (run_type, status, calculation_version, source_id, started_at, finished_at)
               VALUES ('test', 'succeeded', 'serving-dashboard.v1', :source,
                       '2026-02-02T10:00:00Z', '2026-02-02T10:01:00Z') RETURNING id""",
            {"source": catalog["source"]},
        )
        source_key = _one(
            connection,
            """INSERT INTO analytics.dim_sources
                   (source_id, slug, display_name, source_type, country_code, status,
                    is_enabled, source_updated_at)
               SELECT id, slug, display_name, source_type, country_code, status,
                      is_enabled, updated_at FROM ingestion.sources WHERE id=:source
               RETURNING source_key""",
            {"source": catalog["source"]},
        )
        connection.execute(
            sa.text(
                """INSERT INTO analytics.daily_market_metrics
                       (metric_date, source_key, employment_type_code, seniority_level_code,
                        work_mode, active_posting_count, new_posting_count,
                        refresh_run_id, calculation_version)
                   VALUES ('2026-02-01', :source, 'full_time', 'senior', 'hybrid',
                           5, 2, :run, 'serving-dashboard.v1')"""
            ),
            {"source": source_key, "run": analytics_run},
        )
    with engine.connect() as connection:
        row = connection.execute(
            sa.text(
                """SELECT * FROM api.market_overview_v1(
                       '2026-02-01', '2026-02-01', ARRAY[:source]::uuid[])"""
            ),
            {"source": catalog["source"]},
        ).one()
        assert row.active_posting_count == 5
        assert row.new_posting_count == 2
    assert (
        getattr(
            _reject(
                engine,
                "SELECT * FROM api.market_overview_v1('2025-01-01','2026-02-01')",
                {},
            ).orig,
            "sqlstate",
            None,
        )
        == "22023"
    )


def test_security_grants_functions_and_roles(engine: sa.Engine, catalog: dict[str, object]) -> None:
    with engine.connect() as connection:
        properties = connection.execute(
            sa.text(
                """SELECT p.proname, p.prosecdef, p.provolatile, p.proconfig,
                          EXISTS (
                            SELECT 1
                            FROM aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) AS acl
                            WHERE acl.grantee=0 AND acl.privilege_type='EXECUTE'
                          ) AS public_execute,
                          has_function_privilege('anon', p.oid, 'EXECUTE') AS anon_execute,
                          has_function_privilege('authenticated', p.oid, 'EXECUTE')
                            AS authenticated_execute,
                          p.prosrc !~* '\\mEXECUTE\\M' AS has_no_dynamic_sql
                   FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
                   WHERE n.nspname='api'"""
            )
        ).all()
        assert len(properties) == 8
        assert all(row.prosecdef and row.provolatile == "s" for row in properties)
        assert all(row.proconfig == ["search_path=pg_catalog, api, serving"] for row in properties)
        assert all(not row.public_execute for row in properties)
        assert all(row.anon_execute and row.authenticated_execute for row in properties)
        assert all(row.has_no_dynamic_sql for row in properties)
        for role in ("anon", "authenticated"):
            assert not connection.scalar(
                sa.text("SELECT has_schema_privilege(:role, 'serving', 'USAGE')"),
                {"role": role},
            )
            assert (
                connection.scalar(
                    sa.text(
                        """SELECT count(*) FROM pg_class AS relation
                       JOIN pg_namespace AS namespace ON namespace.oid=relation.relnamespace
                       WHERE namespace.nspname='serving'
                         AND relation.relkind IN ('r','v')
                         AND (has_table_privilege(:role, relation.oid, 'SELECT')
                           OR has_table_privilege(:role, relation.oid, 'INSERT')
                           OR has_table_privilege(:role, relation.oid, 'UPDATE')
                           OR has_table_privilege(:role, relation.oid, 'DELETE'))"""
                    ),
                    {"role": role},
                )
                == 0
            )
        assert not connection.scalar(
            sa.text(
                """SELECT has_table_privilege(
                       'service_role', 'serving.job_search_salary_offers',
                       'INSERT,UPDATE,DELETE')"""
            )
        )

    for role in ("anon", "authenticated"):
        role_connection = engine.connect()
        transaction = role_connection.begin()
        try:
            role_connection.execute(sa.text(f"SET ROLE {role}"))
            assert (
                role_connection.scalar(
                    sa.text("SELECT count(*) FROM api.search_jobs_v1(p_query=>'Python')")
                )
                == 1
            )
            with pytest.raises(ProgrammingError):
                role_connection.execute(sa.text("SELECT * FROM serving.job_search_documents"))
        finally:
            transaction.rollback()
            role_connection.close()

    service_connection = engine.connect()
    service_transaction = service_connection.begin()
    try:
        service_connection.execute(sa.text("SET ROLE service_role"))
        assert (
            service_connection.scalar(
                sa.text(
                    "SELECT count(*) FROM serving.job_search_documents WHERE job_posting_id=:job"
                ),
                {"job": catalog["job"]},
            )
            == 1
        )
    finally:
        service_transaction.rollback()
        service_connection.close()


def test_zz_downgrade_and_reupgrade(engine: sa.Engine) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    engine.dispose()
    command.downgrade(config, "20260727_0005")
    check_engine = sa.create_engine(DATABASE_URL)
    try:
        inspector = sa.inspect(check_engine)
        assert "serving" not in inspector.get_schema_names()
        assert "api" not in inspector.get_schema_names()
        assert "analytics" in inspector.get_schema_names()
    finally:
        check_engine.dispose()
    command.upgrade(config, "head")
    reupgraded = sa.create_engine(DATABASE_URL)
    try:
        inspector = sa.inspect(reupgraded)
        assert set(inspector.get_table_names(schema="serving")) == SERVING_TABLES
        assert set(inspector.get_view_names(schema="serving")) == SERVING_VIEWS
    finally:
        reupgraded.dispose()
