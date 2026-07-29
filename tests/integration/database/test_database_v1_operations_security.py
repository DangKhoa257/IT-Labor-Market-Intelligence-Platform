"""PostgreSQL security regression tests for Database V1 Migration 007."""

from __future__ import annotations

import os
from collections.abc import Iterator
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy.exc import IntegrityError

from alembic import command

DATABASE_URL = os.getenv("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql"),
    reason="Database V1 operations integration tests require PostgreSQL",
)
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


@pytest.fixture(scope="module")
def engine() -> Iterator[sa.Engine]:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    command.upgrade(config, "head")
    value = sa.create_engine(DATABASE_URL)
    yield value
    value.dispose()


def test_api_function_security_and_exact_client_grants(engine: sa.Engine) -> None:
    with engine.connect() as connection:
        rows = connection.execute(
            sa.text(
                """SELECT function.proname,function.prosecdef,
                          function.provolatile,function.proconfig,
                          EXISTS (SELECT 1 FROM aclexplode(COALESCE(
                            function.proacl,acldefault('f',function.proowner))) acl
                            WHERE acl.grantee=0 AND acl.privilege_type='EXECUTE'),
                          has_function_privilege('anon',function.oid,'EXECUTE'),
                          has_function_privilege('authenticated',function.oid,'EXECUTE'),
                          has_function_privilege('service_role',function.oid,'EXECUTE')
                FROM pg_proc AS function JOIN pg_namespace AS namespace
                  ON namespace.oid=function.pronamespace WHERE namespace.nspname='api'"""
            )
        ).all()
    assert {row[0] for row in rows} == API_FUNCTIONS
    assert all(row[1] and row[2] == "s" for row in rows)
    assert all(row[3] == ["search_path=pg_catalog, api, serving"] for row in rows)
    assert all(not row[4] and row[5] and row[6] and row[7] for row in rows)


def test_public_and_clients_cannot_access_private_operations(engine: sa.Engine) -> None:
    with engine.connect() as connection:
        for role in ("anon", "authenticated"):
            assert not connection.scalar(
                sa.text("SELECT has_schema_privilege(:role,'operations','USAGE')"), {"role": role}
            )
        assert connection.scalar(
            sa.text("SELECT has_schema_privilege('service_role','operations','USAGE')")
        )
        assert not connection.scalar(
            sa.text(
                """SELECT EXISTS (SELECT 1 FROM pg_namespace AS namespace,
                LATERAL aclexplode(COALESCE(namespace.nspacl,
                  acldefault('n',namespace.nspowner))) acl
                WHERE namespace.nspname='operations' AND acl.grantee=0)"""
            )
        )
        assert connection.scalar(
            sa.text(
                """SELECT has_table_privilege(
                'service_role','operations.backup_snapshots','SELECT,INSERT,UPDATE,DELETE')"""
            )
        )


def test_security_baseline_view_declares_every_violation_category(engine: sa.Engine) -> None:
    expected = {
        "client_private_schema_access",
        "public_private_schema_access",
        "client_private_relation_access",
        "public_private_relation_access",
        "api_relation_present",
        "unsafe_api_function",
        "public_api_execute",
        "missing_api_execute",
        "operations_rls_disabled",
        "operations_client_policy",
        "operations_client_function_execute",
        "operations_public_function_execute",
        "public_schema_create",
    }
    with engine.connect() as connection:
        definition = connection.scalar(
            sa.text(
                "SELECT pg_get_viewdef('operations.v_security_privilege_violations'::regclass,true)"
            )
        )
        assert (
            connection.execute(sa.text("SELECT operations.assert_security_baseline_v1()")).scalar()
            == ""
        )
    assert all(code in definition for code in expected)


@pytest.mark.parametrize(
    ("violation_code", "statement"),
    [
        ("client_private_schema_access", "GRANT USAGE ON SCHEMA operations TO anon"),
        ("public_private_schema_access", "GRANT USAGE ON SCHEMA operations TO PUBLIC"),
        (
            "client_private_relation_access",
            "GRANT SELECT ON operations.partition_policies TO authenticated",
        ),
        (
            "public_private_relation_access",
            "GRANT SELECT ON operations.partition_policies TO PUBLIC",
        ),
        ("api_relation_present", "CREATE TABLE api.security_probe (id integer)"),
        ("unsafe_api_function", "ALTER FUNCTION api.get_job_v1(uuid) SECURITY INVOKER"),
        ("public_api_execute", "GRANT EXECUTE ON FUNCTION api.get_job_v1(uuid) TO PUBLIC"),
        ("missing_api_execute", "REVOKE EXECUTE ON FUNCTION api.get_job_v1(uuid) FROM anon"),
        (
            "operations_rls_disabled",
            "ALTER TABLE operations.partition_policies DISABLE ROW LEVEL SECURITY",
        ),
        (
            "operations_client_policy",
            "CREATE POLICY security_probe ON operations.partition_policies TO anon USING (false)",
        ),
        (
            "operations_client_function_execute",
            "GRANT EXECUTE ON FUNCTION operations.assert_security_baseline_v1() TO anon",
        ),
        (
            "operations_public_function_execute",
            "GRANT EXECUTE ON FUNCTION operations.assert_security_baseline_v1() TO PUBLIC",
        ),
        ("public_schema_create", "GRANT CREATE ON SCHEMA public TO authenticated"),
    ],
)
def test_security_baseline_rejects_each_violation_category(
    engine: sa.Engine, violation_code: str, statement: str
) -> None:
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(sa.text(statement))
            assert connection.scalar(
                sa.text(
                    """SELECT EXISTS (SELECT 1
                    FROM operations.v_security_privilege_violations
                    WHERE violation_code=:code)"""
                ),
                {"code": violation_code},
            )
            with pytest.raises(IntegrityError) as error:
                connection.execute(sa.text("SELECT operations.assert_security_baseline_v1()"))
            assert getattr(error.value.orig, "sqlstate", None) == "23514"
        finally:
            transaction.rollback()


def _protected_rows(connection: sa.Connection) -> dict[str, object]:
    suffix = uuid4().hex
    policy = connection.scalar(
        sa.text(
            """INSERT INTO operations.retention_policies
            (policy_code,target_schema,target_table,record_class,time_column,delete_after_days,
             requires_archive,policy_version,created_by)
            VALUES ('security-finalizer','history','job_status_events','operational_log',
                    'event_at',30,false,'v1','test')
            ON CONFLICT (policy_code) DO UPDATE SET updated_at=now() RETURNING id"""
        ),
    )
    retention = connection.scalar(
        sa.text(
            """INSERT INTO operations.retention_runs
            (policy_id,dry_run,cutoff_at,requested_by)
            VALUES (:policy,false,now(),'test') RETURNING id"""
        ),
        {"policy": policy},
    )
    manifest = connection.scalar(
        sa.text(
            """INSERT INTO operations.archive_manifests
            (target_schema,target_table,archive_format,storage_provider,manifest_uri,
             schema_revision,encryption_method,created_by)
            VALUES ('history','job_observations','jsonl','provider',:uri,'007','none','test')
            RETURNING id"""
        ),
        {"uri": f"s3://bucket/{suffix}"},
    )
    backup = connection.scalar(
        sa.text(
            """INSERT INTO operations.backup_snapshots
            (environment_name,provider,provider_snapshot_id,backup_type,status,postgres_version,
             alembic_revision,database_identifier,recovery_point_at,started_at,finished_at,size_bytes,
             checksum_sha256,storage_uri,encryption_method,encryption_key_reference)
            VALUES ('test','provider',:suffix,'logical','succeeded','16','20260728_0007','db',
                    now(),now()-interval '1 minute',now(),1,repeat('c',64),
                    's3://bucket/backup','kms','kms://key/backup') RETURNING id"""
        ),
        {"suffix": suffix},
    )
    connection.execute(
        sa.text("SELECT operations.finalize_backup_snapshot_v1(:backup,'reviewer')"),
        {"backup": backup},
    )
    restore = connection.scalar(
        sa.text(
            """INSERT INTO operations.restore_drills
            (backup_snapshot_id,environment_name,status,target_alembic_revision,initiated_by,started_at)
            VALUES (:backup,'test','running','20260728_0007','test',now()) RETURNING id"""
        ),
        {"backup": backup},
    )
    health = connection.scalar(
        sa.text(
            """INSERT INTO operations.health_check_runs
            (suite_version,environment_name,status,started_at)
            VALUES ('v1','test','running',now()) RETURNING id"""
        )
    )
    return {
        "retention": retention,
        "manifest": manifest,
        "backup": backup,
        "restore": restore,
        "health": health,
    }


@pytest.mark.parametrize("spoof", ["set_local", "set_config"])
def test_all_five_finalizer_states_reject_service_role_spoof(engine: sa.Engine, spoof: str) -> None:
    with engine.begin() as connection:
        rows = _protected_rows(connection)
    attempts = (
        (
            """UPDATE operations.retention_runs SET status='delete_authorized',started_at=now(),
             delete_authorized_by='spoof',delete_authorized_at=now() WHERE id=:id""",
            rows["retention"],
        ),
        (
            """UPDATE operations.archive_manifests SET status='verified',completed_at=now(),
             manifest_sha256=repeat('a',64),verified_by='spoof',verified_at=now() WHERE id=:id""",
            rows["manifest"],
        ),
        (
            """UPDATE operations.backup_snapshots SET verification_status='verified'
             WHERE id=:id""",
            rows["backup"],
        ),
        (
            """UPDATE operations.restore_drills SET status='succeeded',measured_restore_seconds=1,
             finished_at=now() WHERE id=:id""",
            rows["restore"],
        ),
        (
            """UPDATE operations.health_check_runs SET status='passed',finished_at=now()
             WHERE id=:id""",
            rows["health"],
        ),
    )
    for statement, row_id in attempts:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(sa.text("SET LOCAL ROLE service_role"))
            if spoof == "set_local":
                connection.execute(sa.text("SET LOCAL operations.finalizer='spoof'"))
            else:
                connection.execute(
                    sa.text("SELECT set_config('operations.finalizer','spoof',true)")
                )
            connection.execute(sa.text(statement), {"id": row_id})
