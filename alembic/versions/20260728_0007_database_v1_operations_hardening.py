"""Create Database V1 operational evidence and hardening contracts."""

from alembic import op

revision = "20260728_0007"
down_revision = "20260727_0006"
branch_labels = None
depends_on = None

PRIVATE_SCHEMAS = (
    "system",
    "ingestion",
    "taxonomy",
    "core",
    "history",
    "quality",
    "analytics",
    "serving",
    "operations",
)

OPERATIONS_TABLES = (
    "partition_policies",
    "retention_policies",
    "retention_runs",
    "retention_run_items",
    "archive_manifests",
    "archive_objects",
    "backup_snapshots",
    "restore_drills",
    "restore_drill_checks",
    "maintenance_runs",
    "health_check_runs",
    "health_check_results",
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS operations")
    op.execute("REVOKE ALL ON SCHEMA operations FROM PUBLIC, anon, authenticated")
    op.execute("GRANT USAGE ON SCHEMA operations TO service_role")
    op.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC, anon, authenticated")
    _create_tables()
    _create_table_indexes()
    _create_trigger_functions_and_triggers()
    _seed_partition_policies()
    _create_views()
    _create_remaining_views()
    _create_callable_functions()
    _create_remaining_functions()
    _enable_rls_and_harden_privileges()
    _create_performance_indexes()
    op.execute("SELECT operations.assert_security_baseline_v1()")


def _create_tables() -> None:
    _create_policy_and_retention_tables()
    _create_backup_restore_tables()
    _create_archive_tables()
    _create_maintenance_health_tables()


def _create_policy_and_retention_tables() -> None:
    op.execute(
        """
        CREATE TABLE operations.partition_policies (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            target_schema VARCHAR(63) NOT NULL,
            target_table VARCHAR(63) NOT NULL,
            partition_key VARCHAR(63) NOT NULL,
            partition_strategy VARCHAR(20) DEFAULT 'range' NOT NULL,
            partition_interval VARCHAR(20) DEFAULT 'month' NOT NULL,
            activation_row_threshold BIGINT NOT NULL,
            retention_partition_count INTEGER,
            status VARCHAR(20) DEFAULT 'advisory' NOT NULL,
            approved_by VARCHAR(255), approved_at TIMESTAMPTZ,
            implemented_revision VARCHAR(100), rationale TEXT NOT NULL,
            configuration_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_partition_policies PRIMARY KEY (id),
            CONSTRAINT uq_partition_policies__target UNIQUE (target_schema, target_table),
            CONSTRAINT ck_partition_policies__text CHECK
                (length(trim(target_schema)) > 0 AND length(trim(target_table)) > 0
                 AND length(trim(partition_key)) > 0 AND length(trim(rationale)) > 0),
            CONSTRAINT ck_partition_policies__strategy CHECK
                (partition_strategy IN ('range','list','hash')),
            CONSTRAINT ck_partition_policies__interval CHECK
                (partition_interval IN ('day','week','month','quarter','year','custom')),
            CONSTRAINT ck_partition_policies__status CHECK
                (status IN ('advisory','planned','approved','implemented','disabled')),
            CONSTRAINT ck_partition_policies__threshold CHECK
                (activation_row_threshold > 0 AND
                 (retention_partition_count IS NULL OR retention_partition_count > 0)),
            CONSTRAINT ck_partition_policies__json CHECK
                (jsonb_typeof(configuration_json) = 'object'),
            CONSTRAINT ck_partition_policies__approval CHECK
                (status NOT IN ('approved','implemented') OR
                 (approved_by IS NOT NULL AND length(trim(approved_by)) > 0
                  AND approved_at IS NOT NULL)),
            CONSTRAINT ck_partition_policies__implemented CHECK
                (status != 'implemented' OR
                 (implemented_revision IS NOT NULL
                  AND length(trim(implemented_revision)) > 0))
        )
        """
    )


def _create_archive_tables() -> None:
    op.execute(
        """
        CREATE TABLE operations.archive_manifests (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            retention_run_id UUID,
            target_schema VARCHAR(63) NOT NULL,
            target_table VARCHAR(63) NOT NULL,
            archive_format VARCHAR(20) NOT NULL,
            status VARCHAR(30) DEFAULT 'pending' NOT NULL,
            storage_provider VARCHAR(50) NOT NULL,
            manifest_uri TEXT NOT NULL,
            schema_revision VARCHAR(100) NOT NULL,
            compression VARCHAR(20) DEFAULT 'zstd' NOT NULL,
            encryption_method VARCHAR(50) NOT NULL,
            encryption_key_reference TEXT,
            object_count INTEGER DEFAULT 0 NOT NULL,
            row_count BIGINT DEFAULT 0 NOT NULL,
            byte_count BIGINT DEFAULT 0 NOT NULL,
            min_record_timestamp TIMESTAMPTZ,
            max_record_timestamp TIMESTAMPTZ,
            manifest_sha256 CHAR(64),
            created_by VARCHAR(255) NOT NULL,
            started_at TIMESTAMPTZ, completed_at TIMESTAMPTZ,
            verified_by VARCHAR(255), verified_at TIMESTAMPTZ,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_archive_manifests PRIMARY KEY (id),
            CONSTRAINT fk_archive_manifests__run FOREIGN KEY (retention_run_id)
                REFERENCES operations.retention_runs(id) ON DELETE RESTRICT,
            CONSTRAINT ck_archive_manifests__text CHECK
                (length(trim(target_schema)) > 0 AND length(trim(target_table)) > 0
                 AND length(trim(storage_provider)) > 0 AND length(trim(manifest_uri)) > 0
                 AND length(trim(schema_revision)) > 0
                 AND length(trim(encryption_method)) > 0 AND length(trim(created_by)) > 0),
            CONSTRAINT ck_archive_manifests__format CHECK
                (archive_format IN ('parquet','csv','jsonl')),
            CONSTRAINT ck_archive_manifests__status CHECK
                (status IN ('pending','writing','written','verified','failed','expired')),
            CONSTRAINT ck_archive_manifests__compression CHECK
                (compression IN ('none','gzip','zstd','snappy')),
            CONSTRAINT ck_archive_manifests__uri CHECK
                (manifest_uri !~ '[?#@]'
                 AND manifest_uri !~* 'postgres(ql)?://'
                 AND manifest_uri !~* '(password|token|secret|key)[[:space:]]*='
                 AND manifest_uri !~* '(^|[^a-z0-9])(sk-|eyJ|-----BEGIN)'),
            CONSTRAINT ck_archive_manifests__counts CHECK
                (object_count >= 0 AND row_count >= 0 AND byte_count >= 0),
            CONSTRAINT ck_archive_manifests__bounds CHECK
                ((min_record_timestamp IS NULL) = (max_record_timestamp IS NULL)
                 AND (min_record_timestamp IS NULL
                      OR min_record_timestamp <= max_record_timestamp)),
            CONSTRAINT ck_archive_manifests__sha CHECK
                (manifest_sha256 IS NULL OR manifest_sha256 ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_archive_manifests__encryption CHECK
                (encryption_method = 'none' OR
                 (encryption_key_reference IS NOT NULL
                  AND length(trim(encryption_key_reference)) > 0)),
            CONSTRAINT ck_archive_manifests__completion CHECK
                (status NOT IN ('written','verified') OR completed_at IS NOT NULL),
            CONSTRAINT ck_archive_manifests__verification CHECK
                (status != 'verified' OR
                 (manifest_sha256 IS NOT NULL AND verified_by IS NOT NULL
                  AND length(trim(verified_by)) > 0 AND verified_at IS NOT NULL)),
            CONSTRAINT ck_archive_manifests__failure CHECK
                (status != 'failed' OR
                 (error_message IS NOT NULL AND length(trim(error_message)) > 0))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_archive_manifests__retention_run "
        "ON operations.archive_manifests (retention_run_id) "
        "WHERE retention_run_id IS NOT NULL"
    )
    op.execute(
        """
        CREATE TABLE operations.archive_objects (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            archive_manifest_id UUID NOT NULL,
            sequence_number INTEGER NOT NULL,
            partition_label VARCHAR(255),
            storage_uri TEXT NOT NULL,
            content_type VARCHAR(100) NOT NULL,
            compression VARCHAR(20) NOT NULL,
            status VARCHAR(20) DEFAULT 'pending' NOT NULL,
            row_count BIGINT DEFAULT 0 NOT NULL,
            byte_count BIGINT DEFAULT 0 NOT NULL,
            min_record_timestamp TIMESTAMPTZ,
            max_record_timestamp TIMESTAMPTZ,
            sha256 CHAR(64), provider_etag TEXT,
            verified_at TIMESTAMPTZ, error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_archive_objects PRIMARY KEY (id),
            CONSTRAINT uq_archive_objects__sequence
                UNIQUE (archive_manifest_id, sequence_number),
            CONSTRAINT uq_archive_objects__uri UNIQUE (storage_uri),
            CONSTRAINT fk_archive_objects__manifest FOREIGN KEY (archive_manifest_id)
                REFERENCES operations.archive_manifests(id) ON DELETE RESTRICT,
            CONSTRAINT ck_archive_objects__sequence CHECK (sequence_number >= 0),
            CONSTRAINT ck_archive_objects__text CHECK
                (length(trim(storage_uri)) > 0 AND length(trim(content_type)) > 0),
            CONSTRAINT ck_archive_objects__uri CHECK
                (storage_uri !~ '[?#@]' AND storage_uri !~* 'postgres(ql)?://'
                 AND storage_uri !~* '(password|token|secret|key)[[:space:]]*='
                 AND storage_uri !~* '(^|[^a-z0-9])(sk-|eyJ|-----BEGIN)'),
            CONSTRAINT ck_archive_objects__compression CHECK
                (compression IN ('none','gzip','zstd','snappy')),
            CONSTRAINT ck_archive_objects__status CHECK
                (status IN ('pending','uploaded','verified','failed','expired')),
            CONSTRAINT ck_archive_objects__counts CHECK
                (row_count >= 0 AND byte_count >= 0),
            CONSTRAINT ck_archive_objects__bounds CHECK
                ((min_record_timestamp IS NULL) = (max_record_timestamp IS NULL)
                 AND (min_record_timestamp IS NULL
                      OR min_record_timestamp <= max_record_timestamp)),
            CONSTRAINT ck_archive_objects__sha CHECK
                (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_archive_objects__uploaded CHECK
                (status NOT IN ('uploaded','verified') OR
                 (sha256 IS NOT NULL AND byte_count > 0)),
            CONSTRAINT ck_archive_objects__verified CHECK
                (status != 'verified' OR verified_at IS NOT NULL),
            CONSTRAINT ck_archive_objects__failure CHECK
                (status != 'failed' OR
                 (error_message IS NOT NULL AND length(trim(error_message)) > 0))
        )
        """
    )
    op.execute(
        "ALTER TABLE operations.retention_run_items "
        "ADD CONSTRAINT fk_retention_run_items__archive_object "
        "FOREIGN KEY (archive_object_id) REFERENCES operations.archive_objects(id) "
        "ON DELETE RESTRICT"
    )


def _create_backup_restore_tables() -> None:
    op.execute(
        """
        CREATE TABLE operations.backup_snapshots (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            environment_name VARCHAR(100) NOT NULL,
            provider VARCHAR(50) NOT NULL,
            provider_snapshot_id VARCHAR(255) NOT NULL,
            backup_type VARCHAR(30) NOT NULL,
            status VARCHAR(20) DEFAULT 'requested' NOT NULL,
            verification_status VARCHAR(20) DEFAULT 'pending' NOT NULL,
            postgres_version VARCHAR(50) NOT NULL,
            alembic_revision VARCHAR(100) NOT NULL,
            database_identifier VARCHAR(255) NOT NULL,
            recovery_point_at TIMESTAMPTZ,
            started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
            size_bytes BIGINT, checksum_sha256 CHAR(64), storage_uri TEXT,
            encrypted BOOLEAN DEFAULT true NOT NULL,
            encryption_method VARCHAR(50), encryption_key_reference TEXT,
            retention_until TIMESTAMPTZ,
            verified_by VARCHAR(255), verified_at TIMESTAMPTZ,
            metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_backup_snapshots PRIMARY KEY (id),
            CONSTRAINT uq_backup_snapshots__provider_id
                UNIQUE (provider, provider_snapshot_id),
            CONSTRAINT ck_backup_snapshots__text CHECK
                (length(trim(environment_name)) > 0 AND length(trim(provider)) > 0
                 AND length(trim(provider_snapshot_id)) > 0
                 AND length(trim(postgres_version)) > 0
                 AND length(trim(alembic_revision)) > 0
                 AND length(trim(database_identifier)) > 0),
            CONSTRAINT ck_backup_snapshots__type CHECK (backup_type IN
                ('full','incremental','logical','physical','provider_snapshot',
                 'point_in_time_marker')),
            CONSTRAINT ck_backup_snapshots__status CHECK
                (status IN ('requested','running','succeeded','failed','expired','deleted')),
            CONSTRAINT ck_backup_snapshots__verification_status CHECK
                (verification_status IN ('pending','verified','failed','not_supported')),
            CONSTRAINT ck_backup_snapshots__size CHECK
                (size_bytes IS NULL OR size_bytes >= 0),
            CONSTRAINT ck_backup_snapshots__sha CHECK
                (checksum_sha256 IS NULL OR checksum_sha256 ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_backup_snapshots__uri CHECK
                (storage_uri IS NULL OR
                 (storage_uri !~ '[?#@]'
                  AND storage_uri !~* 'postgres(ql)?://'
                  AND storage_uri !~* '(password|token|secret|key)[[:space:]]*='
                  AND storage_uri !~* '(^|[^a-z0-9])(sk-|eyJ|-----BEGIN)')),
            CONSTRAINT ck_backup_snapshots__json CHECK
                (jsonb_typeof(metadata_json) = 'object'),
            CONSTRAINT ck_backup_snapshots__encryption CHECK
                (NOT encrypted OR
                 (encryption_method IS NOT NULL AND length(trim(encryption_method)) > 0)),
            CONSTRAINT ck_backup_snapshots__key_reference CHECK
                (encryption_key_reference IS NULL OR
                 (encryption_key_reference !~* 'postgres(ql)?://'
                  AND encryption_key_reference !~* '(password|token|secret|key)[[:space:]]*='
                  AND encryption_key_reference !~* '(^|[^a-z0-9])(sk-|eyJ|-----BEGIN)'
                  AND encryption_key_reference !~ '[?#@]')),
            CONSTRAINT ck_backup_snapshots__succeeded CHECK
                (status != 'succeeded' OR
                 (recovery_point_at IS NOT NULL AND started_at IS NOT NULL
                  AND finished_at IS NOT NULL)),
            CONSTRAINT ck_backup_snapshots__failed CHECK
                (status != 'failed' OR
                 (error_message IS NOT NULL AND length(trim(error_message)) > 0)),
            CONSTRAINT ck_backup_snapshots__verified CHECK
                (verification_status != 'verified' OR
                 (status IN ('succeeded','expired','deleted') AND checksum_sha256 IS NOT NULL
                  AND size_bytes > 0 AND storage_uri IS NOT NULL
                  AND verified_by IS NOT NULL AND length(trim(verified_by)) > 0
                  AND verified_at IS NOT NULL)),
            CONSTRAINT ck_backup_snapshots__timestamps CHECK
                ((status='requested' AND started_at IS NULL AND finished_at IS NULL)
                 OR (status='running' AND started_at IS NOT NULL AND finished_at IS NULL)
                 OR (status IN ('succeeded','failed','expired','deleted')
                     AND started_at IS NOT NULL AND finished_at IS NOT NULL
                     AND finished_at >= started_at)),
            CONSTRAINT ck_backup_snapshots__retention CHECK
                (retention_until IS NULL OR recovery_point_at IS NULL
                 OR retention_until > recovery_point_at)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE operations.restore_drills (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            backup_snapshot_id UUID NOT NULL,
            environment_name VARCHAR(100) NOT NULL,
            status VARCHAR(20) DEFAULT 'pending' NOT NULL,
            target_alembic_revision VARCHAR(100) NOT NULL,
            initiated_by VARCHAR(255) NOT NULL,
            rto_target_seconds INTEGER, rpo_target_seconds INTEGER,
            measured_restore_seconds INTEGER, measured_data_loss_seconds INTEGER,
            started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
            notes TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_restore_drills PRIMARY KEY (id),
            CONSTRAINT fk_restore_drills__backup FOREIGN KEY (backup_snapshot_id)
                REFERENCES operations.backup_snapshots(id) ON DELETE RESTRICT,
            CONSTRAINT ck_restore_drills__text CHECK
                (length(trim(environment_name)) > 0
                 AND length(trim(target_alembic_revision)) > 0
                 AND length(trim(initiated_by)) > 0),
            CONSTRAINT ck_restore_drills__status CHECK
                (status IN ('pending','running','succeeded','failed','cancelled')),
            CONSTRAINT ck_restore_drills__seconds CHECK
                ((rto_target_seconds IS NULL OR rto_target_seconds >= 0)
                 AND (rpo_target_seconds IS NULL OR rpo_target_seconds >= 0)
                 AND (measured_restore_seconds IS NULL OR measured_restore_seconds >= 0)
                 AND (measured_data_loss_seconds IS NULL
                      OR measured_data_loss_seconds >= 0)),
            CONSTRAINT ck_restore_drills__timestamps CHECK
                ((status = 'pending' AND started_at IS NULL AND finished_at IS NULL)
                 OR (status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL)
                 OR (status IN ('succeeded','failed','cancelled')
                     AND started_at IS NOT NULL AND finished_at IS NOT NULL
                     AND finished_at >= started_at)),
            CONSTRAINT ck_restore_drills__succeeded CHECK
                (status != 'succeeded' OR measured_restore_seconds IS NOT NULL)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE operations.restore_drill_checks (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            restore_drill_id UUID NOT NULL,
            check_code VARCHAR(100) NOT NULL,
            category VARCHAR(30) NOT NULL,
            severity VARCHAR(20) DEFAULT 'critical' NOT NULL,
            required BOOLEAN DEFAULT true NOT NULL,
            status VARCHAR(20) DEFAULT 'pending' NOT NULL,
            expected_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            actual_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            message TEXT,
            started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_restore_drill_checks PRIMARY KEY (id),
            CONSTRAINT uq_restore_drill_checks__code UNIQUE (restore_drill_id, check_code),
            CONSTRAINT fk_restore_drill_checks__drill FOREIGN KEY (restore_drill_id)
                REFERENCES operations.restore_drills(id) ON DELETE RESTRICT,
            CONSTRAINT ck_restore_drill_checks__code CHECK (length(trim(check_code)) > 0),
            CONSTRAINT ck_restore_drill_checks__category CHECK (category IN
                ('migration','schema','data','constraints','api','security','query',
                 'backup','archive')),
            CONSTRAINT ck_restore_drill_checks__severity CHECK
                (severity IN ('info','warning','error','critical')),
            CONSTRAINT ck_restore_drill_checks__status CHECK
                (status IN ('pending','running','passed','failed','skipped')),
            CONSTRAINT ck_restore_drill_checks__json CHECK
                (jsonb_typeof(expected_json) = 'object'
                 AND jsonb_typeof(actual_json) = 'object'),
            CONSTRAINT ck_restore_drill_checks__finished CHECK
                (status NOT IN ('passed','failed','skipped') OR finished_at IS NOT NULL),
            CONSTRAINT ck_restore_drill_checks__failed CHECK
                (status != 'failed' OR
                 (message IS NOT NULL AND length(trim(message)) > 0)),
            CONSTRAINT ck_restore_drill_checks__skip CHECK
                (NOT (required AND severity = 'critical' AND status = 'skipped'))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE operations.retention_policies (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            policy_code VARCHAR(100) NOT NULL,
            target_schema VARCHAR(63) NOT NULL,
            target_table VARCHAR(63) NOT NULL,
            record_class VARCHAR(50) NOT NULL,
            time_column VARCHAR(63) NOT NULL,
            archive_after_days INTEGER, delete_after_days INTEGER,
            batch_size INTEGER DEFAULT 1000 NOT NULL,
            requires_archive BOOLEAN DEFAULT true NOT NULL,
            legal_hold BOOLEAN DEFAULT false NOT NULL,
            legal_hold_reason TEXT,
            enabled BOOLEAN DEFAULT false NOT NULL,
            policy_version VARCHAR(100) NOT NULL,
            selection_contract_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            created_by VARCHAR(255) NOT NULL,
            approved_by VARCHAR(255), approved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_retention_policies PRIMARY KEY (id),
            CONSTRAINT uq_retention_policies__code UNIQUE (policy_code),
            CONSTRAINT uq_retention_policies__target_class
                UNIQUE (target_schema, target_table, record_class),
            CONSTRAINT ck_retention_policies__text CHECK
                (length(trim(policy_code)) > 0 AND length(trim(target_schema)) > 0
                 AND length(trim(target_table)) > 0 AND length(trim(time_column)) > 0
                 AND length(trim(policy_version)) > 0 AND length(trim(created_by)) > 0),
            CONSTRAINT ck_retention_policies__class CHECK (record_class IN
                ('raw_payload','fetch_event','description_text','temporary_evidence',
                 'operational_log','other')),
            CONSTRAINT ck_retention_policies__windows CHECK
                ((archive_after_days IS NOT NULL OR delete_after_days IS NOT NULL)
                 AND (archive_after_days IS NULL OR archive_after_days >= 0)
                 AND (delete_after_days IS NULL OR delete_after_days >= 0)
                 AND (archive_after_days IS NULL OR delete_after_days IS NULL
                      OR delete_after_days >= archive_after_days)),
            CONSTRAINT ck_retention_policies__batch CHECK (batch_size BETWEEN 1 AND 100000),
            CONSTRAINT ck_retention_policies__json CHECK
                (jsonb_typeof(selection_contract_json) = 'object'),
            CONSTRAINT ck_retention_policies__hold CHECK
                (NOT legal_hold OR
                 (legal_hold_reason IS NOT NULL AND length(trim(legal_hold_reason)) > 0)),
            CONSTRAINT ck_retention_policies__enabled CHECK
                (NOT enabled OR (approved_by IS NOT NULL AND length(trim(approved_by)) > 0
                                 AND approved_at IS NOT NULL))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE operations.retention_runs (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            policy_id UUID NOT NULL,
            status VARCHAR(30) DEFAULT 'pending' NOT NULL,
            dry_run BOOLEAN DEFAULT true NOT NULL,
            cutoff_at TIMESTAMPTZ NOT NULL,
            candidate_count BIGINT DEFAULT 0 NOT NULL,
            archived_count BIGINT DEFAULT 0 NOT NULL,
            deleted_count BIGINT DEFAULT 0 NOT NULL,
            skipped_count BIGINT DEFAULT 0 NOT NULL,
            failed_count BIGINT DEFAULT 0 NOT NULL,
            requested_by VARCHAR(255) NOT NULL,
            delete_authorized_by VARCHAR(255), delete_authorized_at TIMESTAMPTZ,
            started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
            metrics_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_retention_runs PRIMARY KEY (id),
            CONSTRAINT fk_retention_runs__policy FOREIGN KEY (policy_id)
                REFERENCES operations.retention_policies(id) ON DELETE RESTRICT,
            CONSTRAINT ck_retention_runs__status CHECK (status IN
                ('pending','running','archive_pending','archive_verified','delete_authorized',
                 'deleting','succeeded','partially_succeeded','failed','cancelled')),
            CONSTRAINT ck_retention_runs__actor CHECK (length(trim(requested_by)) > 0),
            CONSTRAINT ck_retention_runs__counts CHECK
                (candidate_count >= 0 AND archived_count BETWEEN 0 AND candidate_count
                 AND deleted_count BETWEEN 0 AND candidate_count
                 AND skipped_count BETWEEN 0 AND candidate_count
                 AND failed_count BETWEEN 0 AND candidate_count),
            CONSTRAINT ck_retention_runs__json CHECK (jsonb_typeof(metrics_json) = 'object'),
            CONSTRAINT ck_retention_runs__dry_run CHECK
                (NOT dry_run OR status NOT IN ('delete_authorized','deleting')),
            CONSTRAINT ck_retention_runs__authorization CHECK
                (status != 'delete_authorized' OR
                 (delete_authorized_by IS NOT NULL
                  AND length(trim(delete_authorized_by)) > 0
                  AND delete_authorized_at IS NOT NULL)),
            CONSTRAINT ck_retention_runs__timestamps CHECK
                ((status = 'pending' AND started_at IS NULL AND finished_at IS NULL)
                 OR (status IN ('running','archive_pending','archive_verified',
                                'delete_authorized','deleting')
                     AND started_at IS NOT NULL AND finished_at IS NULL)
                 OR (status IN ('succeeded','partially_succeeded','failed','cancelled')
                     AND started_at IS NOT NULL AND finished_at IS NOT NULL
                     AND finished_at >= started_at))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE operations.retention_run_items (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            retention_run_id UUID NOT NULL,
            target_record_key TEXT NOT NULL,
            record_timestamp TIMESTAMPTZ NOT NULL,
            status VARCHAR(30) DEFAULT 'candidate' NOT NULL,
            archive_object_id BIGINT,
            record_sha256 CHAR(64), error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_retention_run_items PRIMARY KEY (id),
            CONSTRAINT uq_retention_run_items__key
                UNIQUE (retention_run_id, target_record_key),
            CONSTRAINT fk_retention_run_items__run FOREIGN KEY (retention_run_id)
                REFERENCES operations.retention_runs(id) ON DELETE RESTRICT,
            CONSTRAINT ck_retention_run_items__key CHECK
                (length(trim(target_record_key)) > 0),
            CONSTRAINT ck_retention_run_items__status CHECK (status IN
                ('candidate','archived','delete_authorized','deleted','skipped','failed')),
            CONSTRAINT ck_retention_run_items__sha CHECK
                (record_sha256 IS NULL OR record_sha256 ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_retention_run_items__failure CHECK
                (status != 'failed' OR
                 (error_message IS NOT NULL AND length(trim(error_message)) > 0))
        )
        """
    )


def _create_maintenance_health_tables() -> None:
    op.execute(
        """
        CREATE TABLE operations.maintenance_runs (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            run_type VARCHAR(30) NOT NULL,
            target_schema VARCHAR(63), target_table VARCHAR(63),
            status VARCHAR(20) DEFAULT 'pending' NOT NULL,
            dry_run BOOLEAN DEFAULT false NOT NULL,
            requested_by VARCHAR(255) NOT NULL,
            external_job_reference TEXT,
            started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
            rows_examined BIGINT DEFAULT 0 NOT NULL,
            rows_affected BIGINT DEFAULT 0 NOT NULL,
            objects_affected INTEGER DEFAULT 0 NOT NULL,
            metrics_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_maintenance_runs PRIMARY KEY (id),
            CONSTRAINT ck_maintenance_runs__type CHECK (run_type IN
                ('vacuum','analyze','reindex','security_audit','health_check','retention',
                 'archive','backup','restore','partition_review','schema_validation','other')),
            CONSTRAINT ck_maintenance_runs__status CHECK (status IN
                ('pending','running','succeeded','partially_succeeded','failed','cancelled')),
            CONSTRAINT ck_maintenance_runs__actor CHECK (length(trim(requested_by)) > 0),
            CONSTRAINT ck_maintenance_runs__target CHECK
                ((target_schema IS NULL) = (target_table IS NULL)),
            CONSTRAINT ck_maintenance_runs__counts CHECK
                (rows_examined >= 0 AND rows_affected >= 0 AND objects_affected >= 0),
            CONSTRAINT ck_maintenance_runs__json CHECK (jsonb_typeof(metrics_json) = 'object'),
            CONSTRAINT ck_maintenance_runs__reference CHECK
                (external_job_reference IS NULL OR
                 (external_job_reference !~ '[?#@]'
                  AND external_job_reference !~* 'postgres(ql)?://'
                  AND external_job_reference !~* '(password|token|secret|key)[[:space:]]*='
                  AND external_job_reference !~* '(^|[^a-z0-9])(sk-|eyJ|-----BEGIN)')),
            CONSTRAINT ck_maintenance_runs__failure CHECK
                (status != 'failed' OR
                 (error_message IS NOT NULL AND length(trim(error_message)) > 0)),
            CONSTRAINT ck_maintenance_runs__timestamps CHECK
                ((status = 'pending' AND started_at IS NULL AND finished_at IS NULL)
                 OR (status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL)
                 OR (status IN ('succeeded','partially_succeeded','failed','cancelled')
                     AND started_at IS NOT NULL AND finished_at IS NOT NULL
                     AND finished_at >= started_at))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE operations.health_check_runs (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            suite_version VARCHAR(100) NOT NULL,
            environment_name VARCHAR(100) NOT NULL,
            scope VARCHAR(30) DEFAULT 'full' NOT NULL,
            status VARCHAR(30) DEFAULT 'pending' NOT NULL,
            started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
            passed_count INTEGER DEFAULT 0 NOT NULL,
            warning_count INTEGER DEFAULT 0 NOT NULL,
            failed_count INTEGER DEFAULT 0 NOT NULL,
            metrics_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_health_check_runs PRIMARY KEY (id),
            CONSTRAINT ck_health_check_runs__text CHECK
                (length(trim(suite_version)) > 0 AND length(trim(environment_name)) > 0),
            CONSTRAINT ck_health_check_runs__scope CHECK (scope IN
                ('full','security','performance','freshness','backup','restore','quality',
                 'serving','migration')),
            CONSTRAINT ck_health_check_runs__status CHECK (status IN
                ('pending','running','passed','passed_with_warnings','failed','cancelled')),
            CONSTRAINT ck_health_check_runs__counts CHECK
                (passed_count >= 0 AND warning_count >= 0 AND failed_count >= 0),
            CONSTRAINT ck_health_check_runs__json CHECK
                (jsonb_typeof(metrics_json) = 'object'),
            CONSTRAINT ck_health_check_runs__outcome CHECK
                ((status != 'passed' OR (warning_count = 0 AND failed_count = 0))
                 AND (status != 'passed_with_warnings'
                      OR (warning_count > 0 AND failed_count = 0))
                 AND (status != 'failed' OR failed_count > 0)),
            CONSTRAINT ck_health_check_runs__timestamps CHECK
                ((status = 'pending' AND started_at IS NULL AND finished_at IS NULL)
                 OR (status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL)
                 OR (status IN ('passed','passed_with_warnings','failed','cancelled')
                     AND started_at IS NOT NULL AND finished_at IS NOT NULL
                     AND finished_at >= started_at))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE operations.health_check_results (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            health_check_run_id UUID NOT NULL,
            check_code VARCHAR(100) NOT NULL,
            category VARCHAR(30) NOT NULL,
            severity VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL,
            object_schema VARCHAR(63), object_name VARCHAR(255),
            metric_value NUMERIC(30,6), metric_unit VARCHAR(50),
            threshold_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            evidence_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            message TEXT,
            observed_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_health_check_results PRIMARY KEY (id),
            CONSTRAINT fk_health_check_results__run FOREIGN KEY (health_check_run_id)
                REFERENCES operations.health_check_runs(id) ON DELETE RESTRICT,
            CONSTRAINT ck_health_check_results__code CHECK (length(trim(check_code)) > 0),
            CONSTRAINT ck_health_check_results__category CHECK (category IN
                ('security','performance','freshness','backup','restore','quality',
                 'serving','migration','storage')),
            CONSTRAINT ck_health_check_results__severity CHECK
                (severity IN ('info','warning','error','critical')),
            CONSTRAINT ck_health_check_results__status CHECK
                (status IN ('passed','warning','failed','not_applicable')),
            CONSTRAINT ck_health_check_results__json CHECK
                (jsonb_typeof(threshold_json) = 'object'
                 AND jsonb_typeof(evidence_json) = 'object'),
            CONSTRAINT ck_health_check_results__warning CHECK
                (status != 'warning' OR severity IN ('warning','error','critical')),
            CONSTRAINT ck_health_check_results__failed CHECK
                (status != 'failed' OR
                 (severity IN ('error','critical') AND message IS NOT NULL
                  AND length(trim(message)) > 0))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_health_check_results__identity "
        "ON operations.health_check_results "
        "(health_check_run_id, check_code, COALESCE(object_schema, ''), "
        "COALESCE(object_name, ''))"
    )


def _create_table_indexes() -> None:
    statements = (
        "CREATE INDEX ix_partition_policies__status_target ON operations.partition_policies (status, target_schema, target_table)",
        "CREATE INDEX ix_partition_policies__threshold ON operations.partition_policies (activation_row_threshold)",
        "CREATE INDEX ix_retention_policies__enabled_hold ON operations.retention_policies (enabled, legal_hold)",
        "CREATE INDEX ix_retention_policies__target ON operations.retention_policies (target_schema, target_table)",
        "CREATE INDEX ix_retention_policies__version ON operations.retention_policies (policy_version)",
        "CREATE INDEX ix_retention_runs__policy_created ON operations.retention_runs (policy_id, created_at DESC)",
        "CREATE INDEX ix_retention_runs__status_created ON operations.retention_runs (status, created_at DESC)",
        "CREATE INDEX ix_retention_runs__cutoff ON operations.retention_runs (cutoff_at)",
        "CREATE INDEX ix_retention_run_items__run_status ON operations.retention_run_items (retention_run_id, status)",
        "CREATE INDEX ix_retention_run_items__timestamp ON operations.retention_run_items (record_timestamp)",
        "CREATE INDEX ix_retention_run_items__archive_object ON operations.retention_run_items (archive_object_id) WHERE archive_object_id IS NOT NULL",
        "CREATE INDEX ix_archive_manifests__status_created ON operations.archive_manifests (status, created_at DESC)",
        "CREATE INDEX ix_archive_manifests__target_created ON operations.archive_manifests (target_schema, target_table, created_at DESC)",
        "CREATE INDEX ix_archive_manifests__retention_run ON operations.archive_manifests (retention_run_id) WHERE retention_run_id IS NOT NULL",
        "CREATE INDEX ix_archive_manifests__verified_at ON operations.archive_manifests (verified_at DESC) WHERE verified_at IS NOT NULL",
        "CREATE INDEX ix_archive_objects__manifest_sequence ON operations.archive_objects (archive_manifest_id, sequence_number)",
        "CREATE INDEX ix_archive_objects__status_created ON operations.archive_objects (status, created_at DESC)",
        "CREATE INDEX ix_archive_objects__sha ON operations.archive_objects (sha256) WHERE sha256 IS NOT NULL",
        "CREATE INDEX ix_backup_snapshots__environment_recovery ON operations.backup_snapshots (environment_name, recovery_point_at DESC)",
        "CREATE INDEX ix_backup_snapshots__status_created ON operations.backup_snapshots (status, created_at DESC)",
        "CREATE INDEX ix_backup_snapshots__verification ON operations.backup_snapshots (verification_status, verified_at DESC)",
        "CREATE INDEX ix_backup_snapshots__retention ON operations.backup_snapshots (retention_until) WHERE retention_until IS NOT NULL",
        "CREATE INDEX ix_restore_drills__backup_created ON operations.restore_drills (backup_snapshot_id, created_at DESC)",
        "CREATE INDEX ix_restore_drills__status_created ON operations.restore_drills (status, created_at DESC)",
        "CREATE INDEX ix_restore_drills__environment_finished ON operations.restore_drills (environment_name, finished_at DESC)",
        "CREATE INDEX ix_restore_drill_checks__drill_status ON operations.restore_drill_checks (restore_drill_id, status)",
        "CREATE INDEX ix_restore_drill_checks__category_severity_status ON operations.restore_drill_checks (category, severity, status)",
        "CREATE INDEX ix_maintenance_runs__type_created ON operations.maintenance_runs (run_type, created_at DESC)",
        "CREATE INDEX ix_maintenance_runs__status_created ON operations.maintenance_runs (status, created_at DESC)",
        "CREATE INDEX ix_maintenance_runs__target_created ON operations.maintenance_runs (target_schema, target_table, created_at DESC)",
        "CREATE INDEX ix_health_check_runs__environment_created ON operations.health_check_runs (environment_name, created_at DESC)",
        "CREATE INDEX ix_health_check_runs__status_created ON operations.health_check_runs (status, created_at DESC)",
        "CREATE INDEX ix_health_check_runs__scope_created ON operations.health_check_runs (scope, created_at DESC)",
        "CREATE INDEX ix_health_check_results__run_status ON operations.health_check_results (health_check_run_id, status)",
        "CREATE INDEX ix_health_check_results__category_severity_status ON operations.health_check_results (category, severity, status)",
        "CREATE INDEX ix_health_check_results__observed_at ON operations.health_check_results (observed_at DESC)",
    )
    for statement in statements:
        op.execute(statement)


def _create_trigger_functions_and_triggers() -> None:
    op.execute(
        """
        CREATE FUNCTION operations.protect_policy_identity()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, operations AS $$
        DECLARE relation_oid OID; key_name TEXT;
        BEGIN
            relation_oid := to_regclass(NEW.target_schema || '.' || NEW.target_table);
            key_name := CASE WHEN TG_TABLE_NAME = 'partition_policies'
                             THEN to_jsonb(NEW)->>'partition_key'
                             ELSE to_jsonb(NEW)->>'time_column' END;
            IF relation_oid IS NULL OR NOT EXISTS (
                SELECT 1 FROM pg_attribute
                WHERE attrelid = relation_oid
                  AND attname = key_name
                  AND attnum > 0 AND NOT attisdropped
            ) THEN
                RAISE EXCEPTION 'operational policy target or key does not exist'
                    USING ERRCODE = '23514';
            END IF;

            IF TG_OP = 'UPDATE' THEN
                IF TG_TABLE_NAME = 'partition_policies' THEN
                    IF OLD.status IN ('approved','implemented')
                       AND (NEW.target_schema IS DISTINCT FROM OLD.target_schema
                            OR NEW.target_table IS DISTINCT FROM OLD.target_table
                            OR NEW.partition_key IS DISTINCT FROM OLD.partition_key
                            OR NEW.partition_strategy IS DISTINCT FROM OLD.partition_strategy
                            OR NEW.partition_interval IS DISTINCT FROM OLD.partition_interval
                            OR NEW.activation_row_threshold IS DISTINCT FROM
                               OLD.activation_row_threshold) THEN
                        RAISE EXCEPTION 'approved partition policy identity is immutable'
                            USING ERRCODE = '23514';
                    END IF;
                ELSIF TG_TABLE_NAME = 'retention_policies' THEN
                    IF EXISTS (SELECT 1 FROM operations.retention_runs WHERE policy_id = OLD.id)
                       AND (NEW.target_schema IS DISTINCT FROM OLD.target_schema
                            OR NEW.target_table IS DISTINCT FROM OLD.target_table
                            OR NEW.record_class IS DISTINCT FROM OLD.record_class
                            OR NEW.time_column IS DISTINCT FROM OLD.time_column
                            OR NEW.archive_after_days IS DISTINCT FROM OLD.archive_after_days
                            OR NEW.delete_after_days IS DISTINCT FROM OLD.delete_after_days
                            OR NEW.requires_archive IS DISTINCT FROM OLD.requires_archive
                            OR NEW.policy_version IS DISTINCT FROM OLD.policy_version) THEN
                        RAISE EXCEPTION 'referenced retention policy identity is immutable'
                            USING ERRCODE = '23514';
                    END IF;
                    IF OLD.legal_hold AND NOT NEW.legal_hold
                       AND (NEW.policy_version = OLD.policy_version
                            OR NEW.approved_by IS NULL OR NEW.approved_at IS NULL
                            OR NEW.approved_at IS NOT DISTINCT FROM OLD.approved_at) THEN
                        RAISE EXCEPTION 'clearing legal hold requires new approved policy version'
                            USING ERRCODE = '23514';
                    END IF;
                END IF;
            END IF;
            NEW.updated_at := now();
            RETURN NEW;
        END; $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION operations.enforce_run_lifecycle()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, operations AS $$
        DECLARE trusted_finalizer BOOLEAN := current_user = (
            SELECT role.rolname
            FROM pg_proc AS function
            JOIN pg_roles AS role ON role.oid = function.proowner
            WHERE function.oid = 'operations.finalize_backup_snapshot_v1(uuid,text)'::regprocedure
        );
        BEGIN
            IF TG_OP = 'UPDATE' AND TG_TABLE_NAME <> 'backup_snapshots'
               AND NEW.status IS DISTINCT FROM OLD.status
               AND NOT trusted_finalizer THEN
                IF TG_TABLE_NAME = 'retention_runs' AND NOT (
                    (OLD.status='pending' AND NEW.status IN ('running','cancelled')) OR
                    (OLD.status='running' AND NEW.status IN
                        ('archive_pending','archive_verified','failed','cancelled')) OR
                    (OLD.status='archive_pending' AND NEW.status IN
                        ('archive_verified','failed','cancelled')) OR
                    (OLD.status='archive_verified' AND NEW.status IN
                        ('delete_authorized','succeeded','partially_succeeded','failed','cancelled')) OR
                    (OLD.status='delete_authorized' AND NEW.status IN ('deleting','cancelled')) OR
                    (OLD.status='deleting' AND NEW.status IN
                        ('succeeded','partially_succeeded','failed'))
                ) THEN RAISE EXCEPTION 'invalid retention lifecycle transition'
                    USING ERRCODE='23514'; END IF;
                ELSIF TG_TABLE_NAME='archive_manifests' AND NOT (
                    (OLD.status='pending' AND NEW.status IN ('writing','failed','expired')) OR
                    (OLD.status='writing' AND NEW.status IN ('written','failed','expired')) OR
                    (OLD.status='written' AND NEW.status IN ('verified','failed','expired')) OR
                    (OLD.status='verified' AND NEW.status='expired')
                ) THEN RAISE EXCEPTION 'invalid archive lifecycle transition' USING ERRCODE='23514';
                ELSIF TG_TABLE_NAME='restore_drills' AND NOT (
                    (OLD.status='pending' AND NEW.status IN ('running','cancelled')) OR
                    (OLD.status='running' AND NEW.status IN ('succeeded','failed','cancelled'))
                ) THEN RAISE EXCEPTION 'invalid restore lifecycle transition' USING ERRCODE='23514';
                ELSIF TG_TABLE_NAME='maintenance_runs' AND NOT (
                    (OLD.status='pending' AND NEW.status IN ('running','cancelled')) OR
                    (OLD.status='running' AND NEW.status IN
                        ('succeeded','partially_succeeded','failed','cancelled'))
                ) THEN RAISE EXCEPTION 'invalid maintenance lifecycle transition' USING ERRCODE='23514';
                ELSIF TG_TABLE_NAME='health_check_runs' AND NOT (
                    (OLD.status='pending' AND NEW.status IN ('running','cancelled')) OR
                    (OLD.status='running' AND NEW.status IN
                        ('passed','passed_with_warnings','failed','cancelled'))
                ) THEN RAISE EXCEPTION 'invalid health lifecycle transition' USING ERRCODE='23514';
            END IF;

            IF TG_OP='UPDATE' AND TG_TABLE_NAME='backup_snapshots' THEN
                IF NEW.verification_status IS NOT DISTINCT FROM OLD.verification_status
                   AND NEW.status IS DISTINCT FROM OLD.status
                   AND NOT trusted_finalizer
                   AND NOT (
                       (OLD.status='requested' AND NEW.status IN ('running','failed')) OR
                       (OLD.status='running' AND NEW.status IN ('succeeded','failed')) OR
                       (OLD.status='succeeded' AND NEW.status='expired') OR
                       (OLD.status='expired' AND NEW.status='deleted')
                   ) THEN
                    RAISE EXCEPTION 'invalid backup lifecycle transition (trusted %, current %, owner %)',
                        trusted_finalizer, current_user, (
                            SELECT role.rolname FROM pg_proc AS function
                            JOIN pg_roles AS role ON role.oid=function.proowner
                            WHERE function.oid='operations.finalize_backup_snapshot_v1(uuid,text)'::regprocedure
                        ) USING ERRCODE='23514';
                END IF;
            END IF;

            IF TG_OP='UPDATE' THEN
                IF TG_TABLE_NAME='retention_runs' THEN
                    IF (OLD.status<>'pending' OR EXISTS (
                        SELECT 1 FROM operations.retention_run_items WHERE retention_run_id=OLD.id
                    ) OR EXISTS (
                        SELECT 1 FROM operations.archive_manifests WHERE retention_run_id=OLD.id
                    )
                    ) AND (NEW.policy_id IS DISTINCT FROM OLD.policy_id
                         OR NEW.cutoff_at IS DISTINCT FROM OLD.cutoff_at
                         OR NEW.dry_run IS DISTINCT FROM OLD.dry_run) THEN
                        RAISE EXCEPTION 'retention run execution identity is immutable' USING ERRCODE='23514';
                    END IF;
                ELSIF TG_TABLE_NAME='backup_snapshots' THEN
                    IF OLD.status<>'requested' AND (NEW.provider IS DISTINCT FROM OLD.provider
                        OR NEW.provider_snapshot_id IS DISTINCT FROM OLD.provider_snapshot_id
                        OR NEW.backup_type IS DISTINCT FROM OLD.backup_type
                        OR NEW.database_identifier IS DISTINCT FROM OLD.database_identifier
                        OR NEW.postgres_version IS DISTINCT FROM OLD.postgres_version
                        OR NEW.alembic_revision IS DISTINCT FROM OLD.alembic_revision) THEN
                        RAISE EXCEPTION 'backup execution identity is immutable' USING ERRCODE='23514';
                    END IF;
                ELSIF TG_TABLE_NAME='restore_drills' THEN
                    IF (OLD.status<>'pending' OR EXISTS (
                        SELECT 1 FROM operations.restore_drill_checks WHERE restore_drill_id=OLD.id
                    )
                    ) AND (NEW.backup_snapshot_id IS DISTINCT FROM OLD.backup_snapshot_id
                         OR NEW.environment_name IS DISTINCT FROM OLD.environment_name
                         OR NEW.target_alembic_revision IS DISTINCT FROM OLD.target_alembic_revision
                         OR NEW.initiated_by IS DISTINCT FROM OLD.initiated_by
                         OR NEW.rto_target_seconds IS DISTINCT FROM OLD.rto_target_seconds
                         OR NEW.rpo_target_seconds IS DISTINCT FROM OLD.rpo_target_seconds) THEN
                        RAISE EXCEPTION 'restore drill execution identity is immutable' USING ERRCODE='23514';
                    END IF;
                ELSIF TG_TABLE_NAME='health_check_runs' THEN
                    IF (OLD.status<>'pending' OR EXISTS (
                        SELECT 1 FROM operations.health_check_results WHERE health_check_run_id=OLD.id
                    )
                    ) AND (NEW.suite_version IS DISTINCT FROM OLD.suite_version
                         OR NEW.environment_name IS DISTINCT FROM OLD.environment_name
                         OR NEW.scope IS DISTINCT FROM OLD.scope) THEN
                        RAISE EXCEPTION 'health check identity is immutable' USING ERRCODE='23514';
                    END IF;
                ELSIF TG_TABLE_NAME='maintenance_runs' THEN
                    IF OLD.status<>'pending' AND (NEW.run_type IS DISTINCT FROM OLD.run_type
                        OR NEW.target_schema IS DISTINCT FROM OLD.target_schema
                        OR NEW.target_table IS DISTINCT FROM OLD.target_table
                        OR NEW.dry_run IS DISTINCT FROM OLD.dry_run
                        OR NEW.requested_by IS DISTINCT FROM OLD.requested_by) THEN
                        RAISE EXCEPTION 'maintenance execution identity is immutable' USING ERRCODE='23514';
                    END IF;
                END IF;
            END IF;

            IF TG_TABLE_NAME = 'retention_runs' THEN
                IF NEW.status='delete_authorized' AND NOT trusted_finalizer THEN
                    RAISE EXCEPTION 'retention authorization requires finalizer' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME = 'archive_manifests' THEN
                IF NEW.status='verified' AND NOT trusted_finalizer THEN
                    RAISE EXCEPTION 'archive verification requires finalizer' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME = 'backup_snapshots' THEN
                IF NEW.verification_status='verified' AND NOT trusted_finalizer THEN
                    RAISE EXCEPTION 'backup verification requires finalizer' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME = 'restore_drills' THEN
                IF NEW.status='succeeded' AND NOT trusted_finalizer THEN
                    RAISE EXCEPTION 'restore success requires finalizer' USING ERRCODE='23514';
                END IF;
                IF NEW.status='running' AND NOT EXISTS (
                    SELECT 1 FROM operations.backup_snapshots
                    WHERE id=NEW.backup_snapshot_id AND status='succeeded'
                      AND verification_status='verified'
                ) THEN
                    RAISE EXCEPTION 'restore drill requires verified backup' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME = 'health_check_runs'
               AND NEW.status IN ('passed','passed_with_warnings','failed')
               AND NOT trusted_finalizer THEN
                RAISE EXCEPTION 'health outcome requires finalizer' USING ERRCODE='23514';
            END IF;
            NEW.updated_at := now();
            RETURN NEW;
        END; $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION operations.protect_finalized_operational_record()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, operations AS $$
        DECLARE parent_status TEXT; requires_archive BOOLEAN;
                trusted_finalizer BOOLEAN := current_user = (
                    SELECT role.rolname FROM pg_proc AS function
                    JOIN pg_roles AS role ON role.oid=function.proowner
                    WHERE function.oid='operations.finalize_backup_snapshot_v1(uuid,text)'::regprocedure
                );
        BEGIN
            IF TG_TABLE_NAME = 'retention_run_items' THEN
                IF TG_OP='DELETE' THEN
                    SELECT status INTO parent_status FROM operations.retention_runs
                    WHERE id=OLD.retention_run_id FOR UPDATE;
                ELSE
                    SELECT status INTO parent_status FROM operations.retention_runs
                    WHERE id=NEW.retention_run_id FOR UPDATE;
                END IF;
                IF parent_status IN ('succeeded','partially_succeeded','failed','cancelled') THEN
                    RAISE EXCEPTION 'retention items are immutable after terminal completion'
                        USING ERRCODE='23514';
                ELSIF parent_status IN ('delete_authorized','deleting') THEN
                    IF TG_OP!='UPDATE' THEN
                        RAISE EXCEPTION 'only evidence-preserving authorized deletion is allowed'
                            USING ERRCODE='23514';
                    ELSIF OLD.status!='delete_authorized' OR NEW.status!='deleted'
                          OR NEW.retention_run_id IS DISTINCT FROM OLD.retention_run_id
                          OR NEW.target_record_key IS DISTINCT FROM OLD.target_record_key
                          OR NEW.record_timestamp IS DISTINCT FROM OLD.record_timestamp
                          OR NEW.archive_object_id IS DISTINCT FROM OLD.archive_object_id
                          OR NEW.record_sha256 IS DISTINCT FROM OLD.record_sha256
                          OR NEW.error_message IS DISTINCT FROM OLD.error_message
                          OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                        RAISE EXCEPTION 'only evidence-preserving authorized deletion is allowed'
                            USING ERRCODE='23514';
                    END IF;
                END IF;
                SELECT policy.requires_archive INTO requires_archive
                  FROM operations.retention_runs AS run
                  JOIN operations.retention_policies AS policy ON policy.id=run.policy_id
                 WHERE run.id=CASE WHEN TG_OP='DELETE' THEN OLD.retention_run_id
                                   ELSE NEW.retention_run_id END;
                IF TG_OP='INSERT' AND NEW.status!='candidate' THEN
                    RAISE EXCEPTION 'retention items begin as candidates' USING ERRCODE='23514';
                ELSIF TG_OP='UPDATE' THEN
                    IF OLD.status='candidate' AND NOT (
                        NEW.status IN ('skipped','failed')
                        OR (requires_archive AND NEW.status='archived')
                        OR (NOT requires_archive AND NEW.status='delete_authorized'
                            AND trusted_finalizer)
                    ) THEN
                        RAISE EXCEPTION 'invalid candidate retention-item transition'
                            USING ERRCODE='23514';
                    ELSIF OLD.status='archived' AND NOT (
                        NEW.status='delete_authorized' AND trusted_finalizer
                    ) THEN
                        RAISE EXCEPTION 'invalid archived retention-item transition'
                            USING ERRCODE='23514';
                    ELSIF OLD.status='delete_authorized' AND NOT (
                        NEW.status='deleted' AND parent_status IN ('delete_authorized','deleting')
                    ) THEN
                        RAISE EXCEPTION 'invalid authorized retention-item transition'
                            USING ERRCODE='23514';
                    ELSIF OLD.status IN ('skipped','failed','deleted')
                       AND NEW.status IS DISTINCT FROM OLD.status THEN
                        RAISE EXCEPTION 'retention-item terminal status is immutable'
                            USING ERRCODE='23514';
                    END IF;
                END IF;
                IF TG_OP='UPDATE' AND OLD.status='deleted' AND NEW.status!='deleted' THEN
                    RAISE EXCEPTION 'deleted retention evidence is irreversible'
                        USING ERRCODE='23514';
                END IF;
                IF TG_OP <> 'DELETE' AND NEW.status='deleted'
                   AND parent_status NOT IN ('delete_authorized','deleting') THEN
                    RAISE EXCEPTION 'deleted item requires authorized parent'
                        USING ERRCODE='23514';
                END IF;
                IF TG_OP <> 'DELETE' AND NEW.status IN ('archived','delete_authorized','deleted')
                   AND EXISTS (
                       SELECT 1 FROM operations.retention_runs AS run
                       JOIN operations.retention_policies AS policy ON policy.id=run.policy_id
                       WHERE run.id=NEW.retention_run_id AND policy.requires_archive
                         AND NEW.archive_object_id IS NULL
                   ) THEN RAISE EXCEPTION 'archive evidence is required'
                       USING ERRCODE='23514'; END IF;
            ELSIF TG_TABLE_NAME = 'restore_drill_checks' THEN
                IF TG_OP='DELETE' THEN
                    SELECT status INTO parent_status FROM operations.restore_drills
                    WHERE id=OLD.restore_drill_id FOR UPDATE;
                ELSE
                    SELECT status INTO parent_status FROM operations.restore_drills
                    WHERE id=NEW.restore_drill_id FOR UPDATE;
                END IF;
                IF parent_status IN ('succeeded','failed','cancelled') THEN
                    RAISE EXCEPTION 'terminal restore evidence is immutable'
                        USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME = 'health_check_results' THEN
                IF TG_OP='DELETE' THEN
                    SELECT status INTO parent_status FROM operations.health_check_runs
                    WHERE id=OLD.health_check_run_id FOR UPDATE;
                ELSE
                    SELECT status INTO parent_status FROM operations.health_check_runs
                    WHERE id=NEW.health_check_run_id FOR UPDATE;
                END IF;
                IF parent_status IN ('passed','passed_with_warnings','failed','cancelled') THEN
                    RAISE EXCEPTION 'finalized health evidence is immutable'
                        USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME = 'archive_manifests' THEN
                IF TG_OP='UPDATE' AND (OLD.status<>'pending' OR EXISTS (
                    SELECT 1 FROM operations.archive_objects WHERE archive_manifest_id=OLD.id
                )) AND (NEW.retention_run_id IS DISTINCT FROM OLD.retention_run_id
                           OR NEW.target_schema IS DISTINCT FROM OLD.target_schema
                           OR NEW.target_table IS DISTINCT FROM OLD.target_table
                           OR NEW.archive_format IS DISTINCT FROM OLD.archive_format
                           OR NEW.storage_provider IS DISTINCT FROM OLD.storage_provider
                           OR NEW.manifest_uri IS DISTINCT FROM OLD.manifest_uri
                           OR NEW.schema_revision IS DISTINCT FROM OLD.schema_revision
                           OR NEW.compression IS DISTINCT FROM OLD.compression
                           OR NEW.encryption_method IS DISTINCT FROM OLD.encryption_method
                           OR NEW.encryption_key_reference IS DISTINCT FROM OLD.encryption_key_reference) THEN
                    RAISE EXCEPTION 'archive manifest identity is immutable' USING ERRCODE='23514';
                END IF;
                IF OLD.status='verified' THEN
                    RAISE EXCEPTION 'verified archive manifest is immutable' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME = 'backup_snapshots' THEN
                IF OLD.verification_status='verified'
                   AND NOT (TG_OP='UPDATE'
                            AND ((OLD.status='succeeded' AND NEW.status='expired')
                                 OR (OLD.status='expired' AND NEW.status='deleted'))
                            AND NEW.id IS NOT DISTINCT FROM OLD.id
                            AND NEW.environment_name IS NOT DISTINCT FROM OLD.environment_name
                            AND NEW.provider IS NOT DISTINCT FROM OLD.provider
                            AND NEW.provider_snapshot_id IS NOT DISTINCT FROM OLD.provider_snapshot_id
                            AND NEW.backup_type IS NOT DISTINCT FROM OLD.backup_type
                            AND NEW.verification_status IS NOT DISTINCT FROM OLD.verification_status
                            AND NEW.postgres_version IS NOT DISTINCT FROM OLD.postgres_version
                            AND NEW.alembic_revision IS NOT DISTINCT FROM OLD.alembic_revision
                            AND NEW.database_identifier IS NOT DISTINCT FROM OLD.database_identifier
                            AND NEW.recovery_point_at IS NOT DISTINCT FROM OLD.recovery_point_at
                            AND NEW.started_at IS NOT DISTINCT FROM OLD.started_at
                            AND NEW.finished_at IS NOT DISTINCT FROM OLD.finished_at
                            AND NEW.size_bytes IS NOT DISTINCT FROM OLD.size_bytes
                            AND NEW.checksum_sha256 IS NOT DISTINCT FROM OLD.checksum_sha256
                            AND NEW.storage_uri IS NOT DISTINCT FROM OLD.storage_uri
                            AND NEW.encrypted IS NOT DISTINCT FROM OLD.encrypted
                            AND NEW.encryption_method IS NOT DISTINCT FROM OLD.encryption_method
                            AND NEW.encryption_key_reference IS NOT DISTINCT FROM OLD.encryption_key_reference
                            AND NEW.retention_until IS NOT DISTINCT FROM OLD.retention_until
                            AND NEW.verified_by IS NOT DISTINCT FROM OLD.verified_by
                            AND NEW.verified_at IS NOT DISTINCT FROM OLD.verified_at
                            AND NEW.metadata_json IS NOT DISTINCT FROM OLD.metadata_json
                            AND NEW.error_message IS NOT DISTINCT FROM OLD.error_message
                            AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at) THEN
                    RAISE EXCEPTION 'verified backup evidence is immutable' USING ERRCODE='23514';
                END IF;
            ELSIF TG_TABLE_NAME IN ('restore_drills','health_check_runs') THEN
                IF OLD.status IN ('succeeded','failed','cancelled','passed','passed_with_warnings') THEN
                    RAISE EXCEPTION 'terminal operational evidence is immutable' USING ERRCODE='23514';
                END IF;
            END IF;
            IF TG_OP='DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END; $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION operations.protect_archive_object_after_verification()
        RETURNS trigger LANGUAGE plpgsql
        SET search_path = pg_catalog, operations AS $$
        DECLARE manifest_status TEXT;
        BEGIN
            SELECT status INTO manifest_status FROM operations.archive_manifests
            WHERE id=COALESCE(NEW.archive_manifest_id, OLD.archive_manifest_id) FOR UPDATE;
            IF manifest_status='verified' THEN
                RAISE EXCEPTION 'verified archive objects are immutable'
                    USING ERRCODE='23514';
            END IF;
            IF TG_OP='DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END; $$
        """
    )
    for table_name in ("partition_policies", "retention_policies"):
        op.execute(
            f"CREATE TRIGGER trg_{table_name}__protect_policy "
            f"BEFORE INSERT OR UPDATE ON operations.{table_name} "
            "FOR EACH ROW EXECUTE FUNCTION operations.protect_policy_identity()"
        )
    for table_name in (
        "retention_runs",
        "archive_manifests",
        "backup_snapshots",
        "restore_drills",
        "maintenance_runs",
        "health_check_runs",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table_name}__lifecycle "
            f"BEFORE INSERT OR UPDATE ON operations.{table_name} "
            "FOR EACH ROW EXECUTE FUNCTION operations.enforce_run_lifecycle()"
        )
    for table_name in (
        "retention_run_items",
        "archive_manifests",
        "backup_snapshots",
        "restore_drills",
        "restore_drill_checks",
        "health_check_runs",
        "health_check_results",
    ):
        op.execute(
            f"CREATE TRIGGER trg_{table_name}__protect_finalized "
            f"BEFORE INSERT OR UPDATE OR DELETE ON operations.{table_name} "
            "FOR EACH ROW EXECUTE FUNCTION operations.protect_finalized_operational_record()"
        )
    op.execute(
        "CREATE TRIGGER trg_archive_objects__protect_verified "
        "BEFORE INSERT OR UPDATE OR DELETE ON operations.archive_objects "
        "FOR EACH ROW EXECUTE FUNCTION "
        "operations.protect_archive_object_after_verification()"
    )


def _seed_partition_policies() -> None:
    op.execute(
        """
        INSERT INTO operations.partition_policies (
            target_schema, target_table, partition_key, partition_interval,
            activation_row_threshold, rationale
        ) VALUES
            ('history','job_observations','observed_at','month',5000000,
             'Advisory only: review measured observation growth before partitioning.'),
            ('history','job_status_events','event_at','month',2000000,
             'Advisory only: review measured status-event growth before partitioning.'),
            ('history','job_change_events','detected_at','month',5000000,
             'Advisory only: review measured change-event growth before partitioning.'),
            ('analytics','fact_job_observations','loaded_at','month',5000000,
             'Advisory only: review measured job-fact growth before partitioning.'),
            ('analytics','fact_salary_observations','loaded_at','month',5000000,
             'Advisory only: review measured salary-fact growth before partitioning.'),
            ('quality','data_quality_issues','detected_at','quarter',2000000,
             'Advisory only: review measured quality-issue growth before partitioning.')
        """
    )


def _create_views() -> None:
    op.execute(
        """
        CREATE VIEW operations.v_security_privilege_violations AS
        WITH private_schemas(schema_name) AS (VALUES
            ('system'),('ingestion'),('taxonomy'),('core'),('history'),('quality'),
            ('analytics'),('serving'),('operations')
        ), client_roles(role_name) AS (VALUES ('anon'),('authenticated')),
        expected_api(function_name) AS (VALUES
            ('search_jobs_v1'),('get_job_v1'),('market_overview_v1'),
            ('company_hiring_v1'),('location_demand_v1'),('occupation_demand_v1'),
            ('skill_demand_v1'),('salary_metrics_v1')
        )
        SELECT 'client_private_schema_access'::text AS violation_code,
               'critical'::text AS severity, 'schema'::text AS object_type,
               schema_name::text AS object_schema, schema_name::text AS object_name,
               role_name::text AS grantee, 'USAGE_OR_CREATE'::text AS privilege_type,
               '{}'::jsonb AS details
        FROM private_schemas CROSS JOIN client_roles
        WHERE has_schema_privilege(role_name, schema_name, 'USAGE')
           OR has_schema_privilege(role_name, schema_name, 'CREATE')
        UNION ALL
        SELECT 'public_private_schema_access','critical','schema',namespace.nspname,
               namespace.nspname,'PUBLIC',acl.privilege_type,'{}'::jsonb
        FROM pg_namespace AS namespace
        JOIN private_schemas ON schema_name=namespace.nspname
        CROSS JOIN LATERAL aclexplode(
            COALESCE(namespace.nspacl, acldefault('n', namespace.nspowner))) AS acl
        WHERE acl.grantee=0
        UNION ALL
        SELECT 'client_private_relation_access','critical',
               CASE WHEN relation.relkind='S' THEN 'sequence' ELSE 'relation' END,
               namespace.nspname, relation.relname, role_name, 'ANY', '{}'::jsonb
        FROM pg_class AS relation
        JOIN pg_namespace AS namespace ON namespace.oid=relation.relnamespace
        JOIN private_schemas ON schema_name=namespace.nspname
        CROSS JOIN client_roles
        WHERE relation.relkind IN ('r','p','v','m','S') AND (
            has_table_privilege(role_name, relation.oid, 'SELECT') OR
            has_table_privilege(role_name, relation.oid, 'INSERT') OR
            has_table_privilege(role_name, relation.oid, 'UPDATE') OR
            has_table_privilege(role_name, relation.oid, 'DELETE') OR
            (relation.relkind='S' AND has_sequence_privilege(role_name, relation.oid, 'USAGE')))
        UNION ALL
        SELECT 'public_private_relation_access','critical','relation',namespace.nspname,
               relation.relname,'PUBLIC',acl.privilege_type,'{}'::jsonb
        FROM pg_class AS relation
        JOIN pg_namespace AS namespace ON namespace.oid=relation.relnamespace
        JOIN private_schemas ON schema_name=namespace.nspname
        CROSS JOIN LATERAL aclexplode(
            COALESCE(relation.relacl,
                     acldefault(CASE WHEN relation.relkind='S' THEN 'S'::"char"
                                     ELSE 'r'::"char" END, relation.relowner))) AS acl
        WHERE relation.relkind IN ('r','p','v','m','S') AND acl.grantee=0
        UNION ALL
        SELECT 'api_relation_present','critical','relation','api',relation.relname,
               'n/a','n/a','{}'::jsonb
        FROM pg_class AS relation JOIN pg_namespace AS namespace
          ON namespace.oid=relation.relnamespace
        WHERE namespace.nspname='api' AND relation.relkind IN ('r','p','v','m','S')
        UNION ALL
        SELECT 'unsafe_api_function','critical','function','api',function.proname,
               'n/a','SECURITY',jsonb_build_object('security_definer',function.prosecdef,
                   'volatility',function.provolatile,'config',function.proconfig)
        FROM pg_proc AS function JOIN pg_namespace AS namespace
          ON namespace.oid=function.pronamespace
        WHERE namespace.nspname='api' AND (
            NOT function.prosecdef OR function.provolatile!='s'
            OR function.proconfig IS DISTINCT FROM
               ARRAY['search_path=pg_catalog, api, serving']::text[]
            OR function.prosrc ~* '\\mEXECUTE\\M')
        UNION ALL
        SELECT 'public_api_execute','critical','function','api',function.proname,
               'PUBLIC','EXECUTE','{}'::jsonb
        FROM pg_proc AS function JOIN pg_namespace AS namespace
          ON namespace.oid=function.pronamespace
        CROSS JOIN LATERAL aclexplode(
            COALESCE(function.proacl, acldefault('f',function.proowner))) AS acl
        WHERE namespace.nspname='api' AND acl.grantee=0 AND acl.privilege_type='EXECUTE'
        UNION ALL
        SELECT 'missing_api_execute','critical','function','api',function.proname,
               role_name,'EXECUTE','{}'::jsonb
        FROM pg_proc AS function JOIN pg_namespace AS namespace
          ON namespace.oid=function.pronamespace
        JOIN expected_api ON function_name=function.proname CROSS JOIN client_roles
        WHERE namespace.nspname='api'
          AND NOT has_function_privilege(role_name,function.oid,'EXECUTE')
        UNION ALL
        SELECT 'operations_rls_disabled','critical','relation','operations',relation.relname,
               'n/a','RLS','{}'::jsonb
        FROM pg_class AS relation JOIN pg_namespace AS namespace
          ON namespace.oid=relation.relnamespace
        WHERE namespace.nspname='operations' AND relation.relkind='r'
          AND NOT relation.relrowsecurity
        UNION ALL
        SELECT 'operations_client_policy','critical','policy','operations',policy.policyname,
               array_to_string(policy.roles,','),'POLICY','{}'::jsonb
        FROM pg_policies AS policy WHERE policy.schemaname='operations'
        UNION ALL
        SELECT 'operations_client_function_execute','critical','function','operations',
               function.proname,role_name,'EXECUTE','{}'::jsonb
        FROM pg_proc AS function JOIN pg_namespace AS namespace
          ON namespace.oid=function.pronamespace CROSS JOIN client_roles
        WHERE namespace.nspname='operations'
          AND has_function_privilege(role_name,function.oid,'EXECUTE')
        UNION ALL
        SELECT 'operations_public_function_execute','critical','function','operations',
               function.proname,'PUBLIC','EXECUTE','{}'::jsonb
        FROM pg_proc AS function JOIN pg_namespace AS namespace
          ON namespace.oid=function.pronamespace
        CROSS JOIN LATERAL aclexplode(
            COALESCE(function.proacl, acldefault('f',function.proowner))) AS acl
        WHERE namespace.nspname='operations' AND acl.grantee=0
          AND acl.privilege_type='EXECUTE'
        UNION ALL
        SELECT 'public_schema_create','critical','schema','public','public',role_name,
               'CREATE','{}'::jsonb
        FROM (VALUES ('anon'),('authenticated')) AS role(role_name)
        WHERE has_schema_privilege(role_name,'public','CREATE')
        UNION ALL
        SELECT 'public_schema_create','critical','schema','public','public','PUBLIC',
               'CREATE','{}'::jsonb
        FROM pg_namespace AS namespace
        CROSS JOIN LATERAL aclexplode(
            COALESCE(namespace.nspacl, acldefault('n',namespace.nspowner))) AS acl
        WHERE namespace.nspname='public' AND acl.grantee=0
          AND acl.privilege_type='CREATE'
        """
    )
    op.execute(
        """
        CREATE VIEW operations.v_unindexed_foreign_keys AS
        SELECT source_namespace.nspname::text AS table_schema,
               source.relname::text AS table_name,
               foreign_key.conname::text AS constraint_name,
               ARRAY(SELECT attribute.attname::text FROM unnest(foreign_key.conkey)
                     WITH ORDINALITY AS key(attnum, ordinal)
                     JOIN pg_attribute AS attribute
                       ON attribute.attrelid=source.oid AND attribute.attnum=key.attnum
                     ORDER BY key.ordinal)::text[] AS foreign_key_columns,
               target_namespace.nspname::text AS referenced_schema,
               target.relname::text AS referenced_table,
               source.reltuples::bigint AS estimated_rows
        FROM pg_constraint AS foreign_key
        JOIN pg_class AS source ON source.oid=foreign_key.conrelid
        JOIN pg_namespace AS source_namespace ON source_namespace.oid=source.relnamespace
        JOIN pg_class AS target ON target.oid=foreign_key.confrelid
        JOIN pg_namespace AS target_namespace ON target_namespace.oid=target.relnamespace
        WHERE foreign_key.contype='f' AND NOT EXISTS (
            SELECT 1 FROM pg_index AS index
            WHERE index.indrelid=source.oid AND index.indisvalid AND index.indisready
              AND index.indpred IS NULL
              AND (index.indkey::smallint[])[0:cardinality(foreign_key.conkey)-1]
                  = foreign_key.conkey
        )
        """
    )
    op.execute(
        """
        CREATE VIEW operations.v_table_storage_health AS
        SELECT stats.schemaname::text AS table_schema, stats.relname::text AS table_name,
               stats.n_live_tup::bigint AS estimated_live_rows,
               stats.n_dead_tup::bigint AS estimated_dead_rows,
               CASE WHEN stats.n_live_tup + stats.n_dead_tup = 0 THEN 0::numeric
                    ELSE round(stats.n_dead_tup::numeric /
                               (stats.n_live_tup + stats.n_dead_tup), 6) END AS dead_tuple_ratio,
               pg_table_size(stats.relid)::bigint AS table_bytes,
               pg_indexes_size(stats.relid)::bigint AS index_bytes,
               pg_total_relation_size(stats.relid)::bigint AS total_bytes,
               stats.seq_scan::bigint AS sequential_scans,
               stats.idx_scan::bigint AS index_scans,
               stats.last_vacuum, stats.last_autovacuum,
               stats.last_analyze, stats.last_autoanalyze,
               CASE WHEN stats.n_dead_tup > 1000 AND stats.n_dead_tup::numeric /
                              GREATEST(stats.n_live_tup + stats.n_dead_tup,1) > 0.2
                         THEN 'review_dead_tuples'
                    WHEN stats.last_analyze IS NULL AND stats.last_autoanalyze IS NULL
                         AND stats.n_live_tup > 1000 THEN 'review_missing_analyze'
                    WHEN stats.seq_scan > 1000 AND COALESCE(stats.idx_scan,0)=0
                         AND stats.n_live_tup > 10000 THEN 'review_scan_pattern'
                    ELSE 'healthy' END::text AS health_status
        FROM pg_stat_user_tables AS stats
        WHERE stats.schemaname NOT IN ('pg_catalog','information_schema')
        """
    )
    _create_readiness_views()


def _create_readiness_views() -> None:
    op.execute(
        """
        CREATE VIEW operations.v_data_freshness AS
        WITH component(component_name,last_success_at,details) AS (
            SELECT 'history_observation'::text, max(observed_at),
                   jsonb_build_object('source','history.job_observations')
            FROM history.job_observations
            UNION ALL
            SELECT 'quality_validation', max(finished_at),
                   jsonb_build_object('source','quality.validation_runs')
            FROM quality.validation_runs WHERE status IN ('succeeded','partially_succeeded')
            UNION ALL
            SELECT 'analytics_refresh', max(finished_at),
                   jsonb_build_object('source','analytics.refresh_runs')
            FROM analytics.refresh_runs WHERE status IN ('succeeded','partially_succeeded')
            UNION ALL
            SELECT 'serving_refresh', max(finished_at),
                   jsonb_build_object('source','serving.refresh_runs')
            FROM serving.refresh_runs WHERE status IN ('succeeded','partially_succeeded')
        )
        SELECT component_name, last_success_at,
               CASE WHEN last_success_at IS NULL THEN NULL
                    ELSE extract(epoch FROM now()-last_success_at)::bigint END AS age_seconds,
               86400::bigint AS target_age_seconds,
               CASE WHEN last_success_at IS NULL THEN 'never_completed'
                    WHEN now()-last_success_at > interval '1 day' THEN 'stale'
                    ELSE 'fresh' END::text AS status,
               details
        FROM component
        """
    )


def _create_callable_functions() -> None:
    op.execute(
        """
        CREATE FUNCTION operations.assert_security_baseline_v1()
        RETURNS void LANGUAGE plpgsql SECURITY DEFINER STABLE
        SET search_path = pg_catalog, operations AS $$
        BEGIN
            IF EXISTS (SELECT 1 FROM operations.v_security_privilege_violations) THEN
                RAISE EXCEPTION 'Database V1 security baseline violations detected'
                    USING ERRCODE='23514';
            END IF;
        END; $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION operations.authorize_retention_delete_v1(
            p_retention_run_id UUID, p_authorized_by TEXT
        ) RETURNS operations.retention_runs
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, operations AS $$
        DECLARE run operations.retention_runs%ROWTYPE;
                policy operations.retention_policies%ROWTYPE;
                manifest operations.archive_manifests%ROWTYPE;
                item_count BIGINT; archived_count BIGINT; skipped_count BIGINT;
                failed_count BIGINT; authorized_count BIGINT; deleted_count BIGINT;
                candidate_item_count BIGINT; manifest_count BIGINT;
        BEGIN
            IF p_authorized_by IS NULL OR length(trim(p_authorized_by))=0 THEN
                RAISE EXCEPTION 'authorization actor is required' USING ERRCODE='23514';
            END IF;
            SELECT * INTO run FROM operations.retention_runs
            WHERE id=p_retention_run_id FOR UPDATE;
            IF NOT FOUND THEN RAISE EXCEPTION 'retention run not found'
                USING ERRCODE='23514'; END IF;
            SELECT * INTO policy FROM operations.retention_policies
            WHERE id=run.policy_id FOR UPDATE;
            IF NOT policy.enabled OR policy.legal_hold OR run.dry_run
               OR run.candidate_count<=0
               OR (policy.requires_archive AND run.status!='archive_verified')
               OR (NOT policy.requires_archive AND run.status!='running') THEN
                RAISE EXCEPTION 'retention run is not delete-authorizable'
                    USING ERRCODE='23514';
            END IF;
            SELECT count(*), count(*) FILTER (WHERE status='candidate'),
                   count(*) FILTER (WHERE status='archived'),
                   count(*) FILTER (WHERE status='skipped'),
                   count(*) FILTER (WHERE status='failed'),
                   count(*) FILTER (WHERE status='delete_authorized'),
                   count(*) FILTER (WHERE status='deleted')
              INTO item_count, candidate_item_count, archived_count, skipped_count,
                   failed_count, authorized_count, deleted_count
              FROM operations.retention_run_items WHERE retention_run_id=run.id;
            IF item_count != run.candidate_count
               OR archived_count != run.archived_count
               OR skipped_count != run.skipped_count
               OR failed_count != run.failed_count
               OR failed_count != 0 OR authorized_count != 0 OR deleted_count != 0 THEN
                RAISE EXCEPTION 'retention counters do not match item evidence' USING ERRCODE='23514';
            END IF;
            IF policy.requires_archive THEN
                SELECT count(*) INTO manifest_count FROM operations.archive_manifests
                 WHERE retention_run_id=run.id AND status='verified';
                IF manifest_count != 1 THEN
                    RAISE EXCEPTION 'exactly one verified archive manifest is required'
                        USING ERRCODE='23514';
                END IF;
                SELECT * INTO manifest FROM operations.archive_manifests
                 WHERE retention_run_id=run.id AND status='verified' FOR UPDATE;
                IF manifest.target_schema!=policy.target_schema
                   OR manifest.target_table!=policy.target_table
                   OR manifest.row_count!=archived_count
                   OR EXISTS (
                       SELECT 1 FROM operations.retention_run_items AS item
                       LEFT JOIN operations.archive_objects AS object
                         ON object.id=item.archive_object_id
                       WHERE item.retention_run_id=run.id
                         AND item.status!='skipped'
                         AND (item.status!='archived' OR item.record_sha256 IS NULL
                              OR object.archive_manifest_id IS DISTINCT FROM manifest.id
                              OR object.status!='verified')
                   ) THEN
                    RAISE EXCEPTION 'verified archive evidence is incomplete'
                        USING ERRCODE='23514';
                END IF;
            ELSIF archived_count != 0 OR candidate_item_count + skipped_count != item_count THEN
                RAISE EXCEPTION 'no-archive retention evidence is incomplete' USING ERRCODE='23514';
            END IF;
            UPDATE operations.retention_run_items SET status='delete_authorized', updated_at=now()
             WHERE retention_run_id=run.id
               AND status = CASE WHEN policy.requires_archive THEN 'archived' ELSE 'candidate' END;
            UPDATE operations.retention_runs SET status='delete_authorized',
                   delete_authorized_by=trim(p_authorized_by),
                   delete_authorized_at=now(), updated_at=now() WHERE id=run.id
                   RETURNING * INTO run;
            RETURN run;
        END; $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION operations.finalize_archive_manifest_v1(
            p_archive_manifest_id UUID, p_verified_by TEXT
        ) RETURNS operations.archive_manifests
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, operations AS $$
        DECLARE manifest operations.archive_manifests%ROWTYPE;
                aggregate_row RECORD;
        BEGIN
            IF p_verified_by IS NULL OR length(trim(p_verified_by))=0 THEN
                RAISE EXCEPTION 'verification actor is required' USING ERRCODE='23514';
            END IF;
            SELECT * INTO manifest FROM operations.archive_manifests
            WHERE id=p_archive_manifest_id FOR UPDATE;
            IF NOT FOUND OR manifest.status!='written' OR manifest.manifest_sha256 IS NULL THEN
                RAISE EXCEPTION 'archive manifest is not finalizable' USING ERRCODE='23514';
            END IF;
            SELECT count(*)::integer AS object_count, COALESCE(sum(row_count),0)::bigint AS rows,
                   COALESCE(sum(byte_count),0)::bigint AS bytes,
                   min(min_record_timestamp) AS minimum_timestamp,
                   max(max_record_timestamp) AS maximum_timestamp,
                   bool_and(status='verified' AND sha256 IS NOT NULL) AS all_verified
              INTO aggregate_row FROM operations.archive_objects
             WHERE archive_manifest_id=manifest.id;
            IF aggregate_row.object_count=0 OR NOT aggregate_row.all_verified
               OR aggregate_row.object_count!=manifest.object_count
               OR aggregate_row.rows!=manifest.row_count
               OR aggregate_row.bytes!=manifest.byte_count
               OR aggregate_row.minimum_timestamp IS DISTINCT FROM manifest.min_record_timestamp
               OR aggregate_row.maximum_timestamp IS DISTINCT FROM manifest.max_record_timestamp
               OR (manifest.retention_run_id IS NOT NULL AND NOT EXISTS (
                   SELECT 1 FROM operations.retention_runs AS run
                   JOIN operations.retention_policies AS policy ON policy.id=run.policy_id
                   WHERE run.id=manifest.retention_run_id
                     AND policy.target_schema=manifest.target_schema
                     AND policy.target_table=manifest.target_table)) THEN
                RAISE EXCEPTION 'archive manifest evidence mismatch' USING ERRCODE='23514';
            END IF;
            UPDATE operations.archive_manifests SET status='verified',
                   verified_by=trim(p_verified_by), verified_at=now(), updated_at=now()
             WHERE id=manifest.id RETURNING * INTO manifest;
            RETURN manifest;
        END; $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION operations.finalize_backup_snapshot_v1(
            p_backup_snapshot_id UUID, p_verified_by TEXT
        ) RETURNS operations.backup_snapshots
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, operations AS $$
        DECLARE backup operations.backup_snapshots%ROWTYPE;
                current_revision TEXT;
        BEGIN
            IF p_verified_by IS NULL OR length(trim(p_verified_by))=0 THEN
                RAISE EXCEPTION 'verification actor is required' USING ERRCODE='23514';
            END IF;
            SELECT * INTO backup FROM operations.backup_snapshots
            WHERE id=p_backup_snapshot_id FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'backup snapshot not found' USING ERRCODE='23514';
            END IF;
            SELECT version_num INTO current_revision FROM public.alembic_version LIMIT 1;
            IF backup.status!='succeeded'
               OR backup.verification_status!='pending'
               OR backup.recovery_point_at IS NULL OR backup.finished_at IS NULL
               OR COALESCE(backup.size_bytes,0)<=0 OR backup.checksum_sha256 IS NULL
               OR backup.storage_uri IS NULL OR NOT backup.encrypted
               OR backup.encryption_method IS NULL OR length(trim(backup.encryption_method))=0
               OR backup.encryption_key_reference IS NULL
               OR length(trim(backup.encryption_key_reference))=0
               OR (backup.alembic_revision!=current_revision
                   AND NOT (backup.metadata_json @> '{"allow_older_revision": true}'::jsonb)) THEN
                RAISE EXCEPTION 'backup evidence is not verifiable' USING ERRCODE='23514';
            END IF;
            UPDATE operations.backup_snapshots SET verification_status='verified',
                   verified_by=trim(p_verified_by), verified_at=now(), updated_at=now()
             WHERE id=backup.id RETURNING * INTO backup;
            RETURN backup;
        END; $$
        """
    )
    _create_restore_and_health_finalizers()


def _create_restore_and_health_finalizers() -> None:
    op.execute(
        """
        CREATE FUNCTION operations.finalize_restore_drill_v1(p_restore_drill_id UUID)
        RETURNS operations.restore_drills
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, operations AS $$
        DECLARE drill operations.restore_drills%ROWTYPE;
                backup operations.backup_snapshots%ROWTYPE;
                mandatory TEXT[] := ARRAY['alembic_revision','schema_inventory',
                    'row_count_baseline','foreign_key_constraints','api_contract',
                    'security_grants_rls','sample_query_smoke','backup_checksum'];
        BEGIN
            SELECT * INTO drill FROM operations.restore_drills
            WHERE id=p_restore_drill_id FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'restore drill not found' USING ERRCODE='23514';
            END IF;
            SELECT * INTO backup FROM operations.backup_snapshots
             WHERE id=drill.backup_snapshot_id FOR UPDATE;
            IF NOT FOUND OR drill.status!='running' OR drill.measured_restore_seconds IS NULL
               OR NOT FOUND OR backup.status!='succeeded'
               OR backup.verification_status!='verified'
               OR EXISTS (
                   SELECT code FROM unnest(mandatory) AS code
                   WHERE NOT EXISTS (
                       SELECT 1 FROM operations.restore_drill_checks
                       WHERE restore_drill_id=drill.id AND check_code=code
                         AND status='passed'))
               OR EXISTS (
                   SELECT 1 FROM operations.restore_drill_checks
                   WHERE restore_drill_id=drill.id
                     AND ((required AND status!='passed')
                          OR (severity='critical' AND status!='passed')))
               OR NOT EXISTS (
                   SELECT 1 FROM operations.restore_drill_checks
                   WHERE restore_drill_id=drill.id AND check_code='alembic_revision'
                     AND actual_json->>'revision'=drill.target_alembic_revision)
               OR NOT EXISTS (
                   SELECT 1 FROM operations.restore_drill_checks
                    WHERE restore_drill_id=drill.id AND check_code='backup_checksum'
                      AND actual_json->>'checksum'=backup.checksum_sha256) THEN
                RAISE EXCEPTION 'restore drill evidence is incomplete' USING ERRCODE='23514';
            END IF;
            UPDATE operations.restore_drills SET status='succeeded', finished_at=now(),
                   updated_at=now() WHERE id=drill.id RETURNING * INTO drill;
            RETURN drill;
        END; $$
        """
    )


def _callable_signatures() -> tuple[str, ...]:
    return (
        "operations.assert_security_baseline_v1()",
        "operations.authorize_retention_delete_v1(uuid,text)",
        "operations.finalize_archive_manifest_v1(uuid,text)",
        "operations.finalize_backup_snapshot_v1(uuid,text)",
        "operations.finalize_restore_drill_v1(uuid)",
        "operations.finalize_health_check_run_v1(uuid)",
    )


def _enable_rls_and_harden_privileges() -> None:
    for table_name in OPERATIONS_TABLES:
        op.execute(f"ALTER TABLE operations.{table_name} ENABLE ROW LEVEL SECURITY")
    for schema_name in PRIVATE_SCHEMAS:
        op.execute(f"REVOKE ALL ON SCHEMA {schema_name} FROM PUBLIC, anon, authenticated")
        op.execute(
            f"REVOKE ALL ON ALL TABLES IN SCHEMA {schema_name} FROM PUBLIC, anon, authenticated"
        )
        op.execute(
            f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {schema_name} FROM PUBLIC, anon, authenticated"
        )
        op.execute(
            f"REVOKE ALL ON ALL FUNCTIONS IN SCHEMA {schema_name} FROM PUBLIC, anon, authenticated"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} "
            "REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} "
            "REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated"
        )
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} "
            "REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC, anon, authenticated"
        )
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA api REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC")
    op.execute("GRANT USAGE ON SCHEMA operations TO service_role")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA operations TO service_role"
    )
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA operations TO service_role")
    for signature in _callable_signatures():
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC, anon, authenticated")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO service_role")


def _create_performance_indexes() -> None:
    statements = (
        "CREATE INDEX ix_job_observations__observed_at_brin ON history.job_observations USING BRIN (observed_at) WITH (pages_per_range=128)",
        "CREATE INDEX ix_job_status_events__event_at_brin ON history.job_status_events USING BRIN (event_at) WITH (pages_per_range=128)",
        "CREATE INDEX ix_job_change_events__detected_at_brin ON history.job_change_events USING BRIN (detected_at) WITH (pages_per_range=128)",
        "CREATE INDEX ix_job_repost_events__detected_at_brin ON history.job_repost_events USING BRIN (detected_at) WITH (pages_per_range=128)",
        "CREATE INDEX ix_data_quality_issues__detected_at_brin ON quality.data_quality_issues USING BRIN (detected_at) WITH (pages_per_range=128)",
        "CREATE INDEX ix_fact_job_observations__loaded_at_brin ON analytics.fact_job_observations USING BRIN (loaded_at) WITH (pages_per_range=128)",
        "CREATE INDEX ix_fact_salary_observations__loaded_at_brin ON analytics.fact_salary_observations USING BRIN (loaded_at) WITH (pages_per_range=128)",
        "CREATE INDEX ix_data_quality_issues__open_critical ON quality.data_quality_issues (detected_at DESC, issue_code) WHERE status IN ('open','acknowledged') AND severity IN ('error','critical')",
        "CREATE INDEX ix_job_search_documents__active_posted ON serving.job_search_documents (posted_at DESC, job_posting_id) WHERE status='active'",
        "CREATE INDEX ix_analytics_refresh_runs__running ON analytics.refresh_runs (started_at, id) WHERE status='running'",
        "CREATE INDEX ix_serving_refresh_runs__running ON serving.refresh_runs (started_at, id) WHERE status='running'",
    )
    for statement in statements:
        op.execute(statement)


def downgrade() -> None:
    for signature in _callable_signatures():
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM service_role")
        op.execute(f"DROP FUNCTION {signature}")
    for view_name in (
        "v_release_readiness",
        "v_retention_readiness",
        "v_backup_restore_readiness",
        "v_data_freshness",
        "v_table_storage_health",
        "v_unindexed_foreign_keys",
        "v_security_privilege_violations",
    ):
        op.execute(f"DROP VIEW operations.{view_name}")
    for table_name in ("partition_policies", "retention_policies"):
        op.execute(f"DROP TRIGGER trg_{table_name}__protect_policy ON operations.{table_name}")
    for table_name in (
        "retention_runs",
        "archive_manifests",
        "backup_snapshots",
        "restore_drills",
        "maintenance_runs",
        "health_check_runs",
    ):
        op.execute(f"DROP TRIGGER trg_{table_name}__lifecycle ON operations.{table_name}")
    for table_name in (
        "retention_run_items",
        "archive_manifests",
        "backup_snapshots",
        "restore_drills",
        "restore_drill_checks",
        "health_check_runs",
        "health_check_results",
    ):
        op.execute(f"DROP TRIGGER trg_{table_name}__protect_finalized ON operations.{table_name}")
    op.execute("DROP TRIGGER trg_archive_objects__protect_verified ON operations.archive_objects")
    for index_name, schema_name in (
        ("ix_job_observations__observed_at_brin", "history"),
        ("ix_job_status_events__event_at_brin", "history"),
        ("ix_job_change_events__detected_at_brin", "history"),
        ("ix_job_repost_events__detected_at_brin", "history"),
        ("ix_data_quality_issues__detected_at_brin", "quality"),
        ("ix_fact_job_observations__loaded_at_brin", "analytics"),
        ("ix_fact_salary_observations__loaded_at_brin", "analytics"),
        ("ix_data_quality_issues__open_critical", "quality"),
        ("ix_job_search_documents__active_posted", "serving"),
        ("ix_analytics_refresh_runs__running", "analytics"),
        ("ix_serving_refresh_runs__running", "serving"),
    ):
        op.execute(f"DROP INDEX {schema_name}.{index_name}")
    op.execute(
        "ALTER TABLE operations.retention_run_items "
        "DROP CONSTRAINT fk_retention_run_items__archive_object"
    )
    op.execute("DROP TABLE operations.health_check_results")
    op.execute("DROP TABLE operations.health_check_runs")
    op.execute("DROP TABLE operations.maintenance_runs")
    op.execute("DROP TABLE operations.restore_drill_checks")
    op.execute("DROP TABLE operations.restore_drills")
    op.execute("DROP TABLE operations.backup_snapshots")
    op.execute("DROP TABLE operations.retention_run_items")
    op.execute("DROP TABLE operations.archive_objects")
    op.execute("DROP TABLE operations.archive_manifests")
    op.execute("DROP TABLE operations.retention_runs")
    op.execute("DROP TABLE operations.retention_policies")
    op.execute("DROP TABLE operations.partition_policies")
    op.execute("DROP FUNCTION operations.protect_archive_object_after_verification()")
    op.execute("DROP FUNCTION operations.protect_finalized_operational_record()")
    op.execute("DROP FUNCTION operations.enforce_run_lifecycle()")
    op.execute("DROP FUNCTION operations.protect_policy_identity()")
    op.execute("DROP SCHEMA operations")


def _create_remaining_views() -> None:
    op.execute(
        """
        CREATE VIEW operations.v_backup_restore_readiness AS
        WITH environments AS (
            SELECT DISTINCT environment_name FROM operations.backup_snapshots
        ), latest_backup AS (
            SELECT DISTINCT ON (environment_name) environment_name, id, recovery_point_at
            FROM operations.backup_snapshots
            WHERE status='succeeded' AND verification_status='verified'
            ORDER BY environment_name, recovery_point_at DESC
        ), latest_drill AS (
            SELECT DISTINCT ON (environment_name) environment_name, id, finished_at
            FROM operations.restore_drills WHERE status='succeeded'
            ORDER BY environment_name, finished_at DESC
        )
        SELECT environment.environment_name,
               backup.id AS backup_snapshot_id, backup.recovery_point_at,
               CASE WHEN backup.recovery_point_at IS NULL THEN NULL
                    ELSE extract(epoch FROM now()-backup.recovery_point_at)::bigint END
                    AS backup_age_seconds,
               drill.id AS restore_drill_id, drill.finished_at AS restore_drill_finished_at,
               CASE WHEN drill.finished_at IS NULL THEN NULL
                    ELSE extract(epoch FROM now()-drill.finished_at)::bigint END
                    AS restore_drill_age_seconds,
               COALESCE(now()-backup.recovery_point_at <= interval '24 hours',false)
                    AS backup_ready,
               COALESCE(now()-drill.finished_at <= interval '90 days',false)
                    AS restore_ready,
               CASE WHEN backup.id IS NULL THEN 'missing_verified_backup'
                    WHEN now()-backup.recovery_point_at > interval '24 hours'
                         THEN 'stale_backup'
                    WHEN drill.id IS NULL THEN 'missing_restore_drill'
                    WHEN now()-drill.finished_at > interval '90 days'
                         THEN 'stale_restore_drill'
                    ELSE 'ready' END::text AS status
        FROM environments AS environment
        LEFT JOIN latest_backup AS backup USING (environment_name)
        LEFT JOIN latest_drill AS drill USING (environment_name)
        """
    )
    op.execute(
        """
        CREATE VIEW operations.v_retention_readiness AS
        SELECT policy.id AS policy_id, policy.policy_code, policy.target_schema,
               policy.target_table, policy.enabled, policy.legal_hold,
               latest.id AS latest_run_id, latest.status AS latest_run_status,
               latest.candidate_count, latest.archived_count, latest.deleted_count,
               latest.failed_count, latest.created_at AS latest_run_created_at,
               CASE WHEN NOT policy.enabled THEN 'disabled'
                    WHEN policy.legal_hold THEN 'legal_hold'
                    WHEN latest.id IS NULL THEN 'never_run'
                    WHEN latest.status IN ('pending','running','archive_pending',
                                           'delete_authorized','deleting') THEN 'running'
                    WHEN latest.status IN ('succeeded','archive_verified') THEN 'ready'
                    WHEN latest.status='failed' THEN 'failed'
                    ELSE 'needs_review' END::text AS readiness_status
        FROM operations.retention_policies AS policy
        LEFT JOIN LATERAL (
            SELECT run.* FROM operations.retention_runs AS run
            WHERE run.policy_id=policy.id ORDER BY run.created_at DESC LIMIT 1
        ) AS latest ON true
        """
    )
    op.execute(
        """
        CREATE VIEW operations.v_release_readiness AS
        WITH values AS (
            SELECT (SELECT version_num FROM public.alembic_version LIMIT 1)::text
                        AS database_revision,
                   (SELECT count(*) FROM operations.v_security_privilege_violations)::bigint
                        AS security_violation_count,
                   (SELECT count(*) FROM quality.data_quality_issues
                    WHERE status IN ('open','acknowledged') AND severity='critical')::bigint
                        AS open_critical_quality_issue_count,
                   (SELECT count(*) FROM operations.v_data_freshness
                    WHERE status!='fresh')::bigint AS stale_freshness_component_count,
                   ((SELECT count(*) FROM analytics.refresh_runs
                     WHERE status='running' AND started_at < now()-interval '2 hours') +
                    (SELECT count(*) FROM serving.refresh_runs
                     WHERE status='running' AND started_at < now()-interval '2 hours'))::bigint
                        AS stale_running_refresh_count,
                   (SELECT count(DISTINCT environment_name)
                    FROM operations.backup_snapshots
                    WHERE verification_status='verified')::bigint
                        AS verified_backup_environment_count,
                   (SELECT count(*) FROM operations.v_backup_restore_readiness
                    WHERE status='ready')::bigint AS ready_backup_environment_count,
                   (SELECT status FROM operations.health_check_runs
                    WHERE scope='full' ORDER BY created_at DESC LIMIT 1)::text
                        AS latest_health_check_status
        )
        SELECT database_revision, '20260728_0007'::text AS expected_revision,
               security_violation_count, open_critical_quality_issue_count,
               stale_freshness_component_count, stale_running_refresh_count,
               verified_backup_environment_count, ready_backup_environment_count,
               latest_health_check_status,
               (database_revision='20260728_0007' AND security_violation_count=0
                AND open_critical_quality_issue_count=0
                AND stale_freshness_component_count=0 AND stale_running_refresh_count=0
                AND verified_backup_environment_count>0
                AND verified_backup_environment_count=ready_backup_environment_count
                AND COALESCE(latest_health_check_status NOT IN ('failed','cancelled'),true))
                    AS release_ready,
               jsonb_strip_nulls(jsonb_build_object(
                   'revision_mismatch', NULLIF(database_revision='20260728_0007',true),
                   'security_violations', NULLIF(security_violation_count,0),
                   'critical_quality_issues', NULLIF(open_critical_quality_issue_count,0),
                   'stale_freshness_components', NULLIF(stale_freshness_component_count,0),
                   'stale_refreshes', NULLIF(stale_running_refresh_count,0),
                   'backup_metadata_missing',
                       CASE WHEN verified_backup_environment_count=0 THEN true ELSE NULL END,
                   'health_status',
                       CASE WHEN latest_health_check_status IN ('failed','cancelled')
                            THEN latest_health_check_status END)) AS blockers_json,
               now() AS calculated_at
        FROM values
        """
    )


def _create_remaining_functions() -> None:
    op.execute(
        """
        CREATE FUNCTION operations.finalize_health_check_run_v1(p_health_check_run_id UUID)
        RETURNS operations.health_check_runs
        LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, operations AS $$
        DECLARE run operations.health_check_runs%ROWTYPE;
                passed INTEGER; warnings INTEGER; failures INTEGER;
        BEGIN
            SELECT * INTO run FROM operations.health_check_runs
            WHERE id=p_health_check_run_id FOR UPDATE;
            IF NOT FOUND OR run.status!='running' OR NOT EXISTS (
                SELECT 1 FROM operations.health_check_results
                WHERE health_check_run_id=run.id) THEN
                RAISE EXCEPTION 'health check run is not finalizable' USING ERRCODE='23514';
            END IF;
            SELECT count(*) FILTER (WHERE status IN ('passed','not_applicable')),
                   count(*) FILTER (WHERE status='warning'),
                   count(*) FILTER (WHERE status='failed')
              INTO passed,warnings,failures FROM operations.health_check_results
             WHERE health_check_run_id=run.id;
            UPDATE operations.health_check_runs
               SET passed_count=passed, warning_count=warnings, failed_count=failures,
                   status=CASE WHEN failures>0 THEN 'failed'
                               WHEN warnings>0 THEN 'passed_with_warnings'
                               ELSE 'passed' END,
                   finished_at=now(), updated_at=now()
             WHERE id=run.id RETURNING * INTO run;
            RETURN run;
        END; $$
        """
    )
