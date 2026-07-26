"""PostgreSQL integration tests for Database V1 Migration 003."""

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
    reason="Database V1 core integration tests require PostgreSQL",
)

TAXONOMY_TABLES = {
    "taxonomy_versions",
    "employment_types",
    "seniority_levels",
    "occupations",
    "occupation_aliases",
    "skills",
    "skill_aliases",
}
CORE_TABLES = {
    "locations",
    "companies",
    "company_aliases",
    "company_domains",
    "job_postings",
    "job_posting_descriptions",
    "job_posting_locations",
    "salary_offers",
    "job_posting_skills",
    "job_posting_occupations",
}
EMPLOYMENT_CODES = {
    "full_time",
    "part_time",
    "contract",
    "temporary",
    "internship",
    "freelance",
    "other",
    "unknown",
}
SENIORITY_CODES = {
    "intern",
    "entry",
    "junior",
    "mid",
    "senior",
    "lead",
    "manager",
    "director",
    "executive",
    "unknown",
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
        """
        INSERT INTO ingestion.sources (slug, display_name, base_url, status)
        VALUES (:slug, :slug, 'https://example.test', 'approved') RETURNING id
        """,
        {"slug": slug},
    )


def _company(connection: sa.Connection, name: str, normalized: str) -> UUID:
    return _uuid(
        connection,
        """
        INSERT INTO core.companies (canonical_name, normalized_name)
        VALUES (:name, :normalized) RETURNING id
        """,
        {"name": name, "normalized": normalized},
    )


def _location(connection: sa.Connection, key: str, label: str) -> UUID:
    return _uuid(
        connection,
        """
        INSERT INTO core.locations
            (resolution_key, location_type, country_code, canonical_label, normalized_label)
        VALUES (:key, 'city', 'VN', :label, :normalized) RETURNING id
        """,
        {"key": key, "label": label, "normalized": label.casefold()},
    )


def _job(
    connection: sa.Connection,
    source_id: UUID,
    source_job_id: str,
    *,
    company_id: UUID | None = None,
    extracted_record_id: int | None = None,
) -> UUID:
    return _uuid(
        connection,
        """
        INSERT INTO core.job_postings
            (source_id, source_job_id, latest_extracted_record_id, company_id, source_url,
             title_raw, first_seen_at, last_seen_at, last_changed_at)
        VALUES (:source_id, :source_job_id, :record_id, :company_id,
                :source_url, 'Example Engineer',
                now(), now(), now()) RETURNING id
        """,
        {
            "source_id": source_id,
            "source_job_id": source_job_id,
            "source_url": f"https://example.test/jobs/{source_job_id}",
            "record_id": extracted_record_id,
            "company_id": company_id,
        },
    )


@pytest.fixture(scope="module")
def catalog(engine: sa.Engine) -> dict[str, UUID]:
    with engine.begin() as connection:
        source_a = _source(connection, "core-source-a")
        source_b = _source(connection, "core-source-b")
        skill_version = _uuid(
            connection,
            """
            INSERT INTO taxonomy.taxonomy_versions
                (taxonomy_type, version, status, name, valid_from)
            VALUES ('skill', 'SYNTHETIC_TEST_DATA.v1', 'active',
                    'SYNTHETIC_TEST_DATA skills', now()) RETURNING id
            """,
            {},
        )
        occupation_version = _uuid(
            connection,
            """
            INSERT INTO taxonomy.taxonomy_versions
                (taxonomy_type, version, status, name, valid_from)
            VALUES ('occupation', 'SYNTHETIC_TEST_DATA.v1', 'active',
                    'SYNTHETIC_TEST_DATA occupations', now()) RETURNING id
            """,
            {},
        )
        skills = [
            _uuid(
                connection,
                """
                INSERT INTO taxonomy.skills
                    (taxonomy_version_id, canonical_code, canonical_name, normalized_name,
                     skill_type)
                VALUES (:version_id, :code, :name, :normalized, 'programming_language')
                RETURNING id
                """,
                {
                    "version_id": skill_version,
                    "code": f"skill-{index}",
                    "name": name,
                    "normalized": name.casefold(),
                },
            )
            for index, name in enumerate(("Example Python", "Example SQL"), start=1)
        ]
        occupations = [
            _uuid(
                connection,
                """
                INSERT INTO taxonomy.occupations
                    (taxonomy_version_id, canonical_code, canonical_name, normalized_name)
                VALUES (:version_id, :code, :name, :normalized) RETURNING id
                """,
                {
                    "version_id": occupation_version,
                    "code": f"occupation-{index}",
                    "name": name,
                    "normalized": name.casefold(),
                },
            )
            for index, name in enumerate(
                ("Example Developer", "Example Analyst", "Example Architect"), start=1
            )
        ]
        locations = [
            _location(connection, f"synthetic-location-{index}", f"Example City {index}")
            for index in range(1, 4)
        ]
        company_a = _company(connection, "Example Company A", "example company")
        company_b = _company(connection, "Example Company B", "example company")
    return {
        "source_a": source_a,
        "source_b": source_b,
        "skill_1": skills[0],
        "skill_2": skills[1],
        "occupation_1": occupations[0],
        "occupation_2": occupations[1],
        "occupation_3": occupations[2],
        "location_1": locations[0],
        "location_2": locations[1],
        "location_3": locations[2],
        "company_a": company_a,
        "company_b": company_b,
    }


def test_schema_inventory_revision_and_reference_rows(engine: sa.Engine) -> None:
    inspector = sa.inspect(engine)
    assert set(inspector.get_schema_names()) >= {"system", "ingestion", "taxonomy", "core"}
    assert set(inspector.get_table_names(schema="taxonomy")) == TAXONOMY_TABLES
    assert set(inspector.get_table_names(schema="core")) == CORE_TABLES
    with engine.connect() as connection:
        assert (
            connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == "20260726_0003"
        )
        assert (
            set(connection.scalars(sa.text("SELECT code FROM taxonomy.employment_types")))
            == EMPLOYMENT_CODES
        )
        assert (
            set(connection.scalars(sa.text("SELECT code FROM taxonomy.seniority_levels")))
            == SENIORITY_CODES
        )


def test_company_identity_aliases_domains_and_delete_restriction(
    engine: sa.Engine, catalog: dict[str, UUID]
) -> None:
    with engine.begin() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM core.companies WHERE normalized_name='example company'"
                )
            )
            == 2
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO core.company_aliases
                    (company_id, source_id, alias, normalized_alias)
                VALUES (:company, :source, 'Example Co', 'example co')
            """
            ),
            {"company": catalog["company_a"], "source": catalog["source_a"]},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO core.company_aliases
                    (company_id, source_id, alias, normalized_alias)
                VALUES (:company, :source, 'Example Co', 'example co')
            """
            ),
            {"company": catalog["company_b"], "source": catalog["source_a"]},
        )
        job_id = _job(
            connection, catalog["source_a"], "company-restrict", company_id=catalog["company_a"]
        )
    _reject(
        engine, "INSERT INTO core.companies (canonical_name, normalized_name) VALUES (' ', 'x')", {}
    )
    _reject(
        engine,
        """INSERT INTO core.companies
               (canonical_name, normalized_name, employee_count_min, employee_count_max)
           VALUES ('Bad Range', 'bad range', 20, 10)""",
        {},
    )
    _reject(
        engine,
        """INSERT INTO core.company_aliases (company_id, source_id, alias, normalized_alias)
           VALUES (:company, :source, 'Duplicate', 'example co')""",
        {"company": catalog["company_a"], "source": catalog["source_a"]},
    )
    _reject(
        engine,
        """INSERT INTO core.company_domains (company_id, domain)
           VALUES (:company, 'https://example.test/jobs')""",
        {"company": catalog["company_a"]},
    )
    _reject(
        engine,
        "DELETE FROM core.companies WHERE id=:company",
        {"company": catalog["company_a"]},
    )
    with engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM core.job_postings WHERE id=:id"), {"id": job_id})


def test_locations_are_repeatable_and_validated(
    engine: sa.Engine, catalog: dict[str, UUID]
) -> None:
    with engine.begin() as connection:
        job_id = _job(connection, catalog["source_a"], "multi-location")
        connection.execute(
            sa.text(
                """
                INSERT INTO core.job_posting_locations
                    (job_posting_id, location_id, is_primary)
                VALUES (:job, :location, true)
            """
            ),
            {"job": job_id, "location": catalog["location_1"]},
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO core.job_posting_locations (job_posting_id, location_id)
                VALUES (:job, :location)
            """
            ),
            {"job": job_id, "location": catalog["location_2"]},
        )
    _reject(
        engine,
        """INSERT INTO core.locations
               (resolution_key, location_type, latitude, longitude,
                canonical_label, normalized_label)
           VALUES ('bad-latitude', 'city', 91, 106, 'Bad', 'bad')""",
        {},
    )
    _reject(
        engine,
        """INSERT INTO core.locations
               (resolution_key, location_type, latitude, canonical_label, normalized_label)
           VALUES ('missing-longitude', 'city', 10, 'Bad', 'bad')""",
        {},
    )
    _reject(
        engine,
        """INSERT INTO core.locations
               (resolution_key, location_type, canonical_label, normalized_label)
           VALUES ('synthetic-location-1', 'city', 'Duplicate', 'duplicate')""",
        {},
    )
    _reject(
        engine,
        """INSERT INTO core.job_posting_locations
               (job_posting_id, location_id, is_primary)
           VALUES (:job, :location, true)""",
        {"job": job_id, "location": catalog["location_3"]},
    )
    _reject(
        engine,
        """INSERT INTO core.job_posting_locations
               (job_posting_id, location_id, relationship_type, is_remote)
           VALUES (:job, :location, 'applicant_eligible', true)""",
        {"job": job_id, "location": catalog["location_3"]},
    )
    with engine.connect() as connection:
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM core.job_posting_locations WHERE job_posting_id=:job"
                ),
                {"job": job_id},
            )
            == 2
        )


def test_job_source_identity_constraints_and_extracted_lineage(
    engine: sa.Engine, catalog: dict[str, UUID]
) -> None:
    with engine.begin() as connection:
        first_job = _job(connection, catalog["source_a"], "shared-source-id")
        second_job = _job(connection, catalog["source_b"], "shared-source-id")
        parser_id = _uuid(
            connection,
            """INSERT INTO ingestion.parser_versions
                   (source_id, parser_name, version, schema_version)
               VALUES (:source, 'core-test-parser', '1', 'direct.v1') RETURNING id""",
            {"source": catalog["source_a"]},
        )
        run_id = _uuid(
            connection,
            """INSERT INTO ingestion.crawl_runs (source_id, run_type, trigger_type)
               VALUES (:source, 'test', 'test') RETURNING id""",
            {"source": catalog["source_a"]},
        )
        fetch_id = _integer(
            connection,
            """INSERT INTO ingestion.fetch_events
                   (crawl_run_id, source_id, requested_url, http_status, robots_allowed,
                    fetch_outcome, fetched_at)
               VALUES (:run, :source, 'https://example.test/lineage', 200, true,
                       'success', now()) RETURNING id""",
            {"run": run_id, "source": catalog["source_a"]},
        )
        extraction_id = _integer(
            connection,
            """INSERT INTO ingestion.extraction_runs
                   (crawl_run_id, fetch_event_id, parser_version_id)
               VALUES (:run, :fetch, :parser) RETURNING id""",
            {"run": run_id, "fetch": fetch_id, "parser": parser_id},
        )
        record_id = _integer(
            connection,
            """INSERT INTO ingestion.extracted_records
                   (extraction_run_id, source_id, source_job_id, fetch_event_id,
                    record_schema_version, direct_payload_json, direct_hash, extracted_at)
               VALUES (:extraction, :source, 'lineage-job', :fetch,
                       'direct.v1', '{}'::jsonb, :hash, now()) RETURNING id""",
            {
                "extraction": extraction_id,
                "source": catalog["source_a"],
                "fetch": fetch_id,
                "hash": "a" * 64,
            },
        )
        lineage_job = _job(
            connection,
            catalog["source_a"],
            "lineage-job",
            extracted_record_id=record_id,
        )
    _reject(
        engine,
        """INSERT INTO core.job_postings
               (source_id, source_job_id, source_url, title_raw,
                first_seen_at, last_seen_at, last_changed_at)
           VALUES (:source, 'shared-source-id', 'https://example.test/duplicate', 'Duplicate',
                   now(), now(), now())""",
        {"source": catalog["source_a"]},
    )
    invalid_jobs = [
        ("'ftp://example.test/job'", "'Title'", "0", "1", "0.5", "NULL", "now()", "now()"),
        ("'https://example.test/job'", "' '", "0", "1", "0.5", "NULL", "now()", "now()"),
        ("'https://example.test/job'", "'Title'", "-1", "1", "0.5", "NULL", "now()", "now()"),
        ("'https://example.test/job'", "'Title'", "2", "1", "0.5", "NULL", "now()", "now()"),
        ("'https://example.test/job'", "'Title'", "0", "1", "1.1", "NULL", "now()", "now()"),
        ("'https://example.test/job'", "'Title'", "0", "1", "0.5", "'bad'", "now()", "now()"),
        (
            "'https://example.test/job'",
            "'Title'",
            "0",
            "1",
            "0.5",
            "NULL",
            "now()",
            "now() - interval '1 minute'",
        ),
    ]
    for index, (
        url,
        title,
        minimum,
        maximum,
        confidence,
        content_hash,
        first_seen_sql,
        last_seen_sql,
    ) in enumerate(invalid_jobs):
        _reject(
            engine,
            f"""INSERT INTO core.job_postings
                    (source_id, source_job_id, source_url, title_raw,
                     experience_min_years, experience_max_years, confidence_score,
                     source_content_hash, first_seen_at, last_seen_at, last_changed_at)
                VALUES (:source, 'invalid-{index}', {url}, {title}, {minimum}, {maximum},
                        {confidence}, {content_hash}, {first_seen_sql}, {last_seen_sql},
                        {first_seen_sql})""",
            {"source": catalog["source_a"]},
        )
    _reject(
        engine,
        "DELETE FROM ingestion.sources WHERE id=:source",
        {"source": catalog["source_a"]},
    )
    with engine.begin() as connection:
        connection.execute(
            sa.text("DELETE FROM ingestion.extracted_records WHERE id=:record"),
            {"record": record_id},
        )
        assert (
            connection.scalar(
                sa.text("SELECT latest_extracted_record_id FROM core.job_postings WHERE id=:job"),
                {"job": lineage_job},
            )
            is None
        )
        assert {first_job, second_job} <= set(
            connection.scalars(
                sa.text("SELECT id FROM core.job_postings WHERE source_job_id='shared-source-id'")
            )
        )


def test_descriptions_are_current_and_cascade(engine: sa.Engine, catalog: dict[str, UUID]) -> None:
    with engine.begin() as connection:
        job_id = _job(connection, catalog["source_a"], "description-job")
        connection.execute(
            sa.text(
                """INSERT INTO core.job_posting_descriptions
                           (job_posting_id, description_text, content_hash)
                       VALUES (:job, 'EXAMPLE_NOT_REAL_DATA description', :hash)"""
            ),
            {"job": job_id, "hash": "b" * 64},
        )
        empty_job = _job(connection, catalog["source_a"], "empty-description-job")
        hash_job = _job(connection, catalog["source_a"], "bad-description-hash-job")
    _reject(
        engine,
        """INSERT INTO core.job_posting_descriptions
               (job_posting_id, description_text, content_hash)
           VALUES (:job, 'Duplicate', :hash)""",
        {"job": job_id, "hash": "c" * 64},
    )
    _reject(
        engine,
        """INSERT INTO core.job_posting_descriptions
               (job_posting_id, description_text, content_hash)
           VALUES (:job, ' ', :hash)""",
        {"job": empty_job, "hash": "d" * 64},
    )
    _reject(
        engine,
        """INSERT INTO core.job_posting_descriptions
               (job_posting_id, description_text, content_hash)
           VALUES (:job, 'Description', 'invalid')""",
        {"job": hash_job},
    )
    with engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM core.job_postings WHERE id=:job"), {"job": job_id})
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM core.job_posting_descriptions WHERE job_posting_id=:job"
                ),
                {"job": job_id},
            )
            == 0
        )


def test_salary_disclosure_ranges_and_cascade(engine: sa.Engine, catalog: dict[str, UUID]) -> None:
    with engine.begin() as connection:
        job_id = _job(connection, catalog["source_a"], "salary-job")
        connection.execute(
            sa.text(
                """INSERT INTO core.salary_offers
                           (job_posting_id, amount_min, amount_max, currency, period,
                            is_disclosed, tax_basis)
                       VALUES (:job, 1000, 2000, 'USD', 'month', true, 'gross')"""
            ),
            {"job": job_id},
        )
        connection.execute(
            sa.text(
                """INSERT INTO core.salary_offers
                           (job_posting_id, amount_min, amount_max, currency, period, is_disclosed)
                       VALUES (:job, 12000, 24000, 'USD', 'year', true)"""
            ),
            {"job": job_id},
        )
        connection.execute(
            sa.text(
                """INSERT INTO core.salary_offers
                           (job_posting_id, raw_text, is_negotiable)
                       VALUES (:job, 'EXAMPLE_NOT_REAL_DATA negotiable', true)"""
            ),
            {"job": job_id},
        )
    invalid_columns_and_values = [
        ("is_disclosed", "true"),
        ("is_negotiable, amount_min", "true, 1"),
        ("is_disclosed, amount_min", "true, -1"),
        ("is_disclosed, amount_min, amount_max", "true, 2, 1"),
        ("is_disclosed, amount_min, currency", "true, 1, 'usd'"),
        ("fx_rate", "1.0"),
        ("normalized_monthly_min, normalized_monthly_max, is_estimated", "2, 1, true"),
    ]
    for columns, values in invalid_columns_and_values:
        _reject(
            engine,
            f"INSERT INTO core.salary_offers (job_posting_id, {columns}) "
            f"VALUES (:job, {values})",
            {"job": job_id},
        )
    with engine.connect() as connection:
        assert set(
            connection.scalars(
                sa.text(
                    "SELECT period FROM core.salary_offers "
                    "WHERE job_posting_id=:job AND is_disclosed"
                ),
                {"job": job_id},
            )
        ) == {"month", "year"}
    with engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM core.job_postings WHERE id=:job"), {"job": job_id})
        assert (
            connection.scalar(
                sa.text("SELECT count(*) FROM core.salary_offers WHERE job_posting_id=:job"),
                {"job": job_id},
            )
            == 0
        )


def test_skills_requirement_types_alias_scope_and_delete_restriction(
    engine: sa.Engine, catalog: dict[str, UUID]
) -> None:
    with engine.begin() as connection:
        job_id = _job(connection, catalog["source_a"], "skills-job")
        for skill, requirement in (
            (catalog["skill_1"], "required"),
            (catalog["skill_1"], "preferred"),
            (catalog["skill_2"], "mentioned"),
        ):
            connection.execute(
                sa.text(
                    """INSERT INTO core.job_posting_skills
                               (job_posting_id, skill_id, requirement_type)
                           VALUES (:job, :skill, :requirement)"""
                ),
                {"job": job_id, "skill": skill, "requirement": requirement},
            )
        for skill in (catalog["skill_1"], catalog["skill_2"]):
            connection.execute(
                sa.text(
                    """INSERT INTO taxonomy.skill_aliases
                               (skill_id, alias, normalized_alias)
                           VALUES (:skill, 'Example Alias', 'example alias')"""
                ),
                {"skill": skill},
            )
    _reject(
        engine,
        """INSERT INTO core.job_posting_skills (job_posting_id, skill_id, requirement_type)
           VALUES (:job, :skill, 'required')""",
        {"job": job_id, "skill": catalog["skill_1"]},
    )
    _reject(
        engine,
        """INSERT INTO core.job_posting_skills
               (job_posting_id, skill_id, requirement_type, confidence)
           VALUES (:job, :skill, 'mentioned', 1.1)""",
        {"job": job_id, "skill": catalog["skill_1"]},
    )
    _reject(
        engine,
        "DELETE FROM taxonomy.skills WHERE id=:skill",
        {"skill": catalog["skill_1"]},
    )


def test_occupations_primary_secondary_alias_scope_and_delete_restriction(
    engine: sa.Engine, catalog: dict[str, UUID]
) -> None:
    with engine.begin() as connection:
        job_id = _job(connection, catalog["source_a"], "occupations-job")
        connection.execute(
            sa.text(
                """INSERT INTO core.job_posting_occupations
                           (job_posting_id, occupation_id, is_primary)
                       VALUES (:job, :occupation, true)"""
            ),
            {"job": job_id, "occupation": catalog["occupation_1"]},
        )
        connection.execute(
            sa.text(
                """INSERT INTO core.job_posting_occupations
                           (job_posting_id, occupation_id)
                       VALUES (:job, :occupation)"""
            ),
            {"job": job_id, "occupation": catalog["occupation_2"]},
        )
        for occupation in (catalog["occupation_1"], catalog["occupation_2"]):
            connection.execute(
                sa.text(
                    """INSERT INTO taxonomy.occupation_aliases
                               (occupation_id, alias, normalized_alias)
                           VALUES (:occupation, 'Example Role', 'example role')"""
                ),
                {"occupation": occupation},
            )
    _reject(
        engine,
        """INSERT INTO core.job_posting_occupations
               (job_posting_id, occupation_id, is_primary)
           VALUES (:job, :occupation, true)""",
        {"job": job_id, "occupation": catalog["occupation_3"]},
    )
    _reject(
        engine,
        """INSERT INTO core.job_posting_occupations (job_posting_id, occupation_id)
           VALUES (:job, :occupation)""",
        {"job": job_id, "occupation": catalog["occupation_2"]},
    )
    _reject(
        engine,
        "DELETE FROM taxonomy.occupations WHERE id=:occupation",
        {"occupation": catalog["occupation_1"]},
    )


def test_zz_migration_003_downgrade_and_reupgrade(engine: sa.Engine) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.downgrade(config, "20260726_0002")
    inspector = sa.inspect(engine)
    assert "taxonomy" not in inspector.get_schema_names()
    assert "core" not in inspector.get_schema_names()
    assert "sources" in inspector.get_table_names(schema="ingestion")
    assert "pipeline_versions" in inspector.get_table_names(schema="system")
    command.upgrade(config, "head")
    inspector = sa.inspect(engine)
    assert set(inspector.get_table_names(schema="taxonomy")) == TAXONOMY_TABLES
    assert set(inspector.get_table_names(schema="core")) == CORE_TABLES
