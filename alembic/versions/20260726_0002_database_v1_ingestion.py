"""Create Database V1 ingestion execution and evidence lineage."""

from alembic import op

revision = "20260726_0002"
down_revision = "20260726_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ingestion.crawl_runs (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            source_id UUID NOT NULL,
            source_policy_id UUID,
            parser_version_id UUID,
            pipeline_version_id UUID,
            run_type VARCHAR(30) DEFAULT 'scheduled' NOT NULL,
            trigger_type VARCHAR(30) DEFAULT 'manual' NOT NULL,
            status VARCHAR(30) DEFAULT 'pending' NOT NULL,
            requested_limit INTEGER,
            configuration_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            git_commit_sha VARCHAR(64),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            discovered_count INTEGER DEFAULT 0 NOT NULL,
            task_count INTEGER DEFAULT 0 NOT NULL,
            fetch_success_count INTEGER DEFAULT 0 NOT NULL,
            fetch_failure_count INTEGER DEFAULT 0 NOT NULL,
            unchanged_count INTEGER DEFAULT 0 NOT NULL,
            extracted_count INTEGER DEFAULT 0 NOT NULL,
            accepted_count INTEGER DEFAULT 0 NOT NULL,
            rejected_count INTEGER DEFAULT 0 NOT NULL,
            error_count INTEGER DEFAULT 0 NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_crawl_runs PRIMARY KEY (id),
            CONSTRAINT fk_crawl_runs__source_id__sources FOREIGN KEY (source_id)
                REFERENCES ingestion.sources(id) ON DELETE RESTRICT,
            CONSTRAINT fk_crawl_runs__source_policy_id__source_policies FOREIGN KEY (source_policy_id)
                REFERENCES ingestion.source_policies(id) ON DELETE SET NULL,
            CONSTRAINT fk_crawl_runs__parser_version_id__parser_versions FOREIGN KEY (parser_version_id)
                REFERENCES ingestion.parser_versions(id) ON DELETE SET NULL,
            CONSTRAINT fk_crawl_runs__pipeline_version_id__pipeline_versions FOREIGN KEY (pipeline_version_id)
                REFERENCES system.pipeline_versions(id) ON DELETE SET NULL,
            CONSTRAINT ck_crawl_runs__run_type CHECK
                (run_type IN ('scheduled','manual','backfill','recheck','reprocess','import','test')),
            CONSTRAINT ck_crawl_runs__trigger_type CHECK
                (trigger_type IN ('manual','scheduler','github_actions','api','system','test')),
            CONSTRAINT ck_crawl_runs__status CHECK (status IN
                ('pending','running','succeeded','partially_succeeded','failed','cancelled','skipped')),
            CONSTRAINT ck_crawl_runs__requested_limit CHECK
                (requested_limit IS NULL OR requested_limit >= 1),
            CONSTRAINT ck_crawl_runs__counters CHECK
                (discovered_count >= 0 AND task_count >= 0 AND fetch_success_count >= 0
                 AND fetch_failure_count >= 0 AND unchanged_count >= 0 AND extracted_count >= 0
                 AND accepted_count >= 0 AND rejected_count >= 0 AND error_count >= 0),
            CONSTRAINT ck_crawl_runs__timestamps CHECK
                (finished_at IS NULL OR (started_at IS NOT NULL AND finished_at >= started_at)),
            CONSTRAINT ck_crawl_runs__running_started CHECK (status != 'running' OR started_at IS NOT NULL),
            CONSTRAINT ck_crawl_runs__terminal_finished CHECK
                (status NOT IN ('succeeded','partially_succeeded','failed','cancelled','skipped')
                 OR finished_at IS NOT NULL),
            CONSTRAINT ck_crawl_runs__git_commit_sha CHECK
                (git_commit_sha IS NULL OR git_commit_sha ~ '^[0-9a-fA-F]{7,64}$')
        )
    """
    )
    op.execute(
        "CREATE INDEX ix_crawl_runs__source_id_started_at ON ingestion.crawl_runs (source_id, started_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_crawl_runs__status_created_at ON ingestion.crawl_runs (status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_crawl_runs__parser_version_id ON ingestion.crawl_runs (parser_version_id)"
    )
    op.execute(
        "CREATE INDEX ix_crawl_runs__pipeline_version_id ON ingestion.crawl_runs (pipeline_version_id)"
    )

    op.execute(
        """
        CREATE TABLE ingestion.crawl_tasks (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            crawl_run_id UUID NOT NULL,
            source_id UUID NOT NULL,
            task_type VARCHAR(30) NOT NULL,
            status VARCHAR(30) DEFAULT 'pending' NOT NULL,
            priority SMALLINT DEFAULT 0 NOT NULL,
            source_job_id VARCHAR(255),
            requested_url TEXT,
            discovery_method VARCHAR(150),
            attempt_count INTEGER DEFAULT 0 NOT NULL,
            max_attempts INTEGER DEFAULT 1 NOT NULL,
            scheduled_for TIMESTAMPTZ,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            task_payload_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_crawl_tasks PRIMARY KEY (id),
            CONSTRAINT fk_crawl_tasks__crawl_run_id__crawl_runs FOREIGN KEY (crawl_run_id)
                REFERENCES ingestion.crawl_runs(id) ON DELETE CASCADE,
            CONSTRAINT fk_crawl_tasks__source_id__sources FOREIGN KEY (source_id)
                REFERENCES ingestion.sources(id) ON DELETE RESTRICT,
            CONSTRAINT uq_crawl_tasks__run_type_url UNIQUE (crawl_run_id, task_type, requested_url),
            CONSTRAINT ck_crawl_tasks__task_type CHECK (task_type IN
                ('discovery','listing_page','detail_page','api_page','sitemap','recheck','reprocess','other')),
            CONSTRAINT ck_crawl_tasks__status CHECK
                (status IN ('pending','running','succeeded','failed','cancelled','skipped')),
            CONSTRAINT ck_crawl_tasks__priority CHECK (priority BETWEEN -32768 AND 32767),
            CONSTRAINT ck_crawl_tasks__attempts CHECK
                (attempt_count >= 0 AND max_attempts >= 1 AND attempt_count <= max_attempts),
            CONSTRAINT ck_crawl_tasks__target CHECK
                (requested_url IS NOT NULL OR source_job_id IS NOT NULL),
            CONSTRAINT ck_crawl_tasks__timestamps CHECK
                (finished_at IS NULL OR (started_at IS NOT NULL AND finished_at >= started_at))
        )
    """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_crawl_tasks__run_type_source_job ON ingestion.crawl_tasks (crawl_run_id, task_type, source_job_id) WHERE source_job_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_crawl_tasks__run_status_priority ON ingestion.crawl_tasks (crawl_run_id, status, priority DESC, id)"
    )
    op.execute(
        "CREATE INDEX ix_crawl_tasks__source_id_source_job_id ON ingestion.crawl_tasks (source_id, source_job_id) WHERE source_job_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_crawl_tasks__status_scheduled_for ON ingestion.crawl_tasks (status, scheduled_for)"
    )

    op.execute(
        """
        CREATE TABLE ingestion.raw_objects (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            sha256 CHAR(64) NOT NULL,
            storage_provider VARCHAR(30) NOT NULL,
            bucket_name VARCHAR(255),
            object_key TEXT,
            inline_payload_json JSONB,
            compression VARCHAR(20) DEFAULT 'none' NOT NULL,
            mime_type VARCHAR(255),
            byte_size BIGINT NOT NULL,
            redaction_status VARCHAR(30) DEFAULT 'not_required' NOT NULL,
            retention_policy_id UUID,
            expires_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_raw_objects PRIMARY KEY (id),
            CONSTRAINT fk_raw_objects__retention_policy_id__retention_policies
                FOREIGN KEY (retention_policy_id) REFERENCES system.retention_policies(id) ON DELETE SET NULL,
            CONSTRAINT uq_raw_objects__sha256 UNIQUE (sha256),
            CONSTRAINT ck_raw_objects__sha256 CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_raw_objects__storage_provider CHECK (storage_provider IN
                ('inline','supabase_storage','filesystem','s3_compatible','github_artifact','other')),
            CONSTRAINT ck_raw_objects__compression CHECK
                (compression IN ('none','gzip','zstd','zip','other')),
            CONSTRAINT ck_raw_objects__redaction_status CHECK
                (redaction_status IN ('not_required','pending','redacted','failed')),
            CONSTRAINT ck_raw_objects__byte_size CHECK (byte_size >= 0),
            CONSTRAINT ck_raw_objects__storage_consistency CHECK
                ((storage_provider = 'inline' AND inline_payload_json IS NOT NULL
                  AND bucket_name IS NULL AND object_key IS NULL)
                 OR (storage_provider != 'inline' AND object_key IS NOT NULL))
        )
    """
    )
    op.execute(
        "CREATE INDEX ix_raw_objects__expires_at ON ingestion.raw_objects (expires_at) WHERE expires_at IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_raw_objects__retention_policy_id ON ingestion.raw_objects (retention_policy_id)"
    )
    op.execute("CREATE INDEX ix_raw_objects__created_at ON ingestion.raw_objects (created_at DESC)")

    op.execute(
        """
        CREATE TABLE ingestion.fetch_events (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            crawl_run_id UUID NOT NULL,
            crawl_task_id BIGINT,
            source_id UUID NOT NULL,
            raw_object_id BIGINT,
            requested_url TEXT NOT NULL,
            resolved_url TEXT,
            http_method VARCHAR(10) DEFAULT 'GET' NOT NULL,
            http_status SMALLINT,
            content_type VARCHAR(255),
            response_bytes BIGINT,
            duration_ms INTEGER,
            attempt_number INTEGER DEFAULT 1 NOT NULL,
            robots_allowed BOOLEAN,
            fetch_outcome VARCHAR(30) NOT NULL,
            etag TEXT,
            last_modified TEXT,
            request_headers_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            response_headers_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            fetched_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_fetch_events PRIMARY KEY (id),
            CONSTRAINT fk_fetch_events__crawl_run_id__crawl_runs FOREIGN KEY (crawl_run_id)
                REFERENCES ingestion.crawl_runs(id) ON DELETE CASCADE,
            CONSTRAINT fk_fetch_events__crawl_task_id__crawl_tasks FOREIGN KEY (crawl_task_id)
                REFERENCES ingestion.crawl_tasks(id) ON DELETE SET NULL,
            CONSTRAINT fk_fetch_events__source_id__sources FOREIGN KEY (source_id)
                REFERENCES ingestion.sources(id) ON DELETE RESTRICT,
            CONSTRAINT fk_fetch_events__raw_object_id__raw_objects FOREIGN KEY (raw_object_id)
                REFERENCES ingestion.raw_objects(id) ON DELETE SET NULL,
            CONSTRAINT ck_fetch_events__method CHECK (http_method IN ('GET','HEAD')),
            CONSTRAINT ck_fetch_events__http_status CHECK
                (http_status IS NULL OR http_status BETWEEN 100 AND 599),
            CONSTRAINT ck_fetch_events__metrics CHECK
                ((response_bytes IS NULL OR response_bytes >= 0)
                 AND (duration_ms IS NULL OR duration_ms >= 0) AND attempt_number >= 1),
            CONSTRAINT ck_fetch_events__outcome CHECK (fetch_outcome IN
                ('success','http_error','network_error','timeout','blocked_by_policy',
                 'robots_disallowed','invalid_content','cancelled','other_error')),
            CONSTRAINT ck_fetch_events__success_status CHECK
                (fetch_outcome != 'success'
                 OR (http_status IS NOT NULL AND http_status BETWEEN 200 AND 399)),
            CONSTRAINT ck_fetch_events__robots_outcome CHECK
                (fetch_outcome != 'robots_disallowed' OR robots_allowed IS FALSE)
        )
    """
    )
    op.execute(
        "CREATE INDEX ix_fetch_events__run_fetched_at ON ingestion.fetch_events (crawl_run_id, fetched_at)"
    )
    op.execute(
        "CREATE INDEX ix_fetch_events__source_id_fetched_at ON ingestion.fetch_events (source_id, fetched_at DESC)"
    )
    op.execute("CREATE INDEX ix_fetch_events__task_id ON ingestion.fetch_events (crawl_task_id)")
    op.execute(
        "CREATE INDEX ix_fetch_events__http_status ON ingestion.fetch_events (http_status) WHERE http_status IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_fetch_events__outcome_fetched_at ON ingestion.fetch_events (fetch_outcome, fetched_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_fetch_events__raw_object_id ON ingestion.fetch_events (raw_object_id) WHERE raw_object_id IS NOT NULL"
    )

    op.execute(
        """
        CREATE TABLE ingestion.extraction_runs (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            crawl_run_id UUID,
            fetch_event_id BIGINT NOT NULL,
            raw_object_id BIGINT,
            parser_version_id UUID NOT NULL,
            status VARCHAR(30) DEFAULT 'pending' NOT NULL,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            record_count INTEGER DEFAULT 0 NOT NULL,
            warning_count INTEGER DEFAULT 0 NOT NULL,
            error_count INTEGER DEFAULT 0 NOT NULL,
            metrics_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_extraction_runs PRIMARY KEY (id),
            CONSTRAINT fk_extraction_runs__crawl_run_id__crawl_runs FOREIGN KEY (crawl_run_id)
                REFERENCES ingestion.crawl_runs(id) ON DELETE SET NULL,
            CONSTRAINT fk_extraction_runs__fetch_event_id__fetch_events FOREIGN KEY (fetch_event_id)
                REFERENCES ingestion.fetch_events(id) ON DELETE CASCADE,
            CONSTRAINT fk_extraction_runs__raw_object_id__raw_objects FOREIGN KEY (raw_object_id)
                REFERENCES ingestion.raw_objects(id) ON DELETE SET NULL,
            CONSTRAINT fk_extraction_runs__parser_version_id__parser_versions FOREIGN KEY (parser_version_id)
                REFERENCES ingestion.parser_versions(id) ON DELETE RESTRICT,
            CONSTRAINT uq_extraction_runs__fetch_parser UNIQUE (fetch_event_id, parser_version_id),
            CONSTRAINT ck_extraction_runs__status CHECK (status IN
                ('pending','running','succeeded','partially_succeeded','failed','cancelled','skipped')),
            CONSTRAINT ck_extraction_runs__counters CHECK
                (record_count >= 0 AND warning_count >= 0 AND error_count >= 0),
            CONSTRAINT ck_extraction_runs__timestamps CHECK
                (finished_at IS NULL OR (started_at IS NOT NULL AND finished_at >= started_at)),
            CONSTRAINT ck_extraction_runs__running_started CHECK (status != 'running' OR started_at IS NOT NULL)
        )
    """
    )
    op.execute(
        "CREATE INDEX ix_extraction_runs__parser_version_id_created_at ON ingestion.extraction_runs (parser_version_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_extraction_runs__status_created_at ON ingestion.extraction_runs (status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_extraction_runs__crawl_run_id ON ingestion.extraction_runs (crawl_run_id)"
    )

    op.execute(
        """
        CREATE TABLE ingestion.extracted_records (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            extraction_run_id BIGINT NOT NULL,
            source_id UUID NOT NULL,
            source_job_id VARCHAR(255) NOT NULL,
            fetch_event_id BIGINT NOT NULL,
            raw_object_id BIGINT,
            record_schema_version VARCHAR(100) NOT NULL,
            direct_payload_json JSONB NOT NULL,
            direct_hash CHAR(64) NOT NULL,
            processing_status VARCHAR(30) DEFAULT 'pending' NOT NULL,
            rejection_reason TEXT,
            extracted_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_extracted_records PRIMARY KEY (id),
            CONSTRAINT fk_extracted_records__extraction_run_id__extraction_runs FOREIGN KEY (extraction_run_id)
                REFERENCES ingestion.extraction_runs(id) ON DELETE CASCADE,
            CONSTRAINT fk_extracted_records__source_id__sources FOREIGN KEY (source_id)
                REFERENCES ingestion.sources(id) ON DELETE RESTRICT,
            CONSTRAINT fk_extracted_records__fetch_event_id__fetch_events FOREIGN KEY (fetch_event_id)
                REFERENCES ingestion.fetch_events(id) ON DELETE CASCADE,
            CONSTRAINT fk_extracted_records__raw_object_id__raw_objects FOREIGN KEY (raw_object_id)
                REFERENCES ingestion.raw_objects(id) ON DELETE SET NULL,
            CONSTRAINT uq_extracted_records__run_source_identity
                UNIQUE (extraction_run_id, source_id, source_job_id),
            CONSTRAINT ck_extracted_records__identity_not_blank CHECK
                (length(trim(source_job_id)) > 0 AND length(trim(record_schema_version)) > 0),
            CONSTRAINT ck_extracted_records__direct_hash CHECK (direct_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_extracted_records__processing_status CHECK (processing_status IN
                ('pending','accepted','rejected','quarantined','processed','superseded')),
            CONSTRAINT ck_extracted_records__rejection_reason CHECK
                (processing_status IN ('rejected','quarantined') OR rejection_reason IS NULL),
            CONSTRAINT ck_extracted_records__payload_object CHECK
                (jsonb_typeof(direct_payload_json) = 'object')
        )
    """
    )
    op.execute(
        "CREATE INDEX ix_extracted_records__source_identity ON ingestion.extracted_records (source_id, source_job_id)"
    )
    op.execute(
        "CREATE INDEX ix_extracted_records__processing_status_created_at ON ingestion.extracted_records (processing_status, created_at)"
    )
    op.execute(
        "CREATE INDEX ix_extracted_records__fetch_event_id ON ingestion.extracted_records (fetch_event_id)"
    )
    op.execute(
        "CREATE INDEX ix_extracted_records__direct_hash ON ingestion.extracted_records (direct_hash)"
    )

    op.execute(
        """
        CREATE TABLE ingestion.crawl_errors (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            crawl_run_id UUID NOT NULL,
            crawl_task_id BIGINT,
            fetch_event_id BIGINT,
            extraction_run_id BIGINT,
            source_id UUID NOT NULL,
            stage VARCHAR(30) NOT NULL,
            category VARCHAR(50) NOT NULL,
            error_code VARCHAR(150),
            retryable BOOLEAN DEFAULT false NOT NULL,
            severity VARCHAR(20) DEFAULT 'error' NOT NULL,
            source_job_id VARCHAR(255),
            url TEXT,
            http_status SMALLINT,
            sanitized_message TEXT NOT NULL,
            details_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            occurred_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_crawl_errors PRIMARY KEY (id),
            CONSTRAINT fk_crawl_errors__crawl_run_id__crawl_runs FOREIGN KEY (crawl_run_id)
                REFERENCES ingestion.crawl_runs(id) ON DELETE CASCADE,
            CONSTRAINT fk_crawl_errors__crawl_task_id__crawl_tasks FOREIGN KEY (crawl_task_id)
                REFERENCES ingestion.crawl_tasks(id) ON DELETE SET NULL,
            CONSTRAINT fk_crawl_errors__fetch_event_id__fetch_events FOREIGN KEY (fetch_event_id)
                REFERENCES ingestion.fetch_events(id) ON DELETE SET NULL,
            CONSTRAINT fk_crawl_errors__extraction_run_id__extraction_runs FOREIGN KEY (extraction_run_id)
                REFERENCES ingestion.extraction_runs(id) ON DELETE SET NULL,
            CONSTRAINT fk_crawl_errors__source_id__sources FOREIGN KEY (source_id)
                REFERENCES ingestion.sources(id) ON DELETE RESTRICT,
            CONSTRAINT ck_crawl_errors__stage CHECK (stage IN
                ('policy','discovery','task','fetch','raw_storage','extraction','validation','processing','other')),
            CONSTRAINT ck_crawl_errors__category CHECK (category IN
                ('robots_disallowed','policy_blocked','http_error','network_error','timeout',
                 'invalid_url','invalid_content','parse_error','schema_error','storage_error',
                 'database_error','rate_limited','unexpected')),
            CONSTRAINT ck_crawl_errors__severity CHECK
                (severity IN ('info','warning','error','critical')),
            CONSTRAINT ck_crawl_errors__http_status CHECK
                (http_status IS NULL OR http_status BETWEEN 100 AND 599),
            CONSTRAINT ck_crawl_errors__message_not_blank CHECK
                (length(trim(sanitized_message)) > 0),
            CONSTRAINT ck_crawl_errors__context CHECK
                (crawl_task_id IS NOT NULL OR fetch_event_id IS NOT NULL
                 OR extraction_run_id IS NOT NULL OR url IS NOT NULL OR source_job_id IS NOT NULL)
        )
    """
    )
    op.execute(
        "CREATE INDEX ix_crawl_errors__run_occurred_at ON ingestion.crawl_errors (crawl_run_id, occurred_at)"
    )
    op.execute(
        "CREATE INDEX ix_crawl_errors__source_stage_category ON ingestion.crawl_errors (source_id, stage, category)"
    )
    op.execute(
        "CREATE INDEX ix_crawl_errors__retryable_occurred_at ON ingestion.crawl_errors (retryable, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_crawl_errors__severity_occurred_at ON ingestion.crawl_errors (severity, occurred_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE ingestion.crawl_errors")
    op.execute("DROP TABLE ingestion.extracted_records")
    op.execute("DROP TABLE ingestion.extraction_runs")
    op.execute("DROP TABLE ingestion.fetch_events")
    op.execute("DROP TABLE ingestion.raw_objects")
    op.execute("DROP TABLE ingestion.crawl_tasks")
    op.execute("DROP TABLE ingestion.crawl_runs")
