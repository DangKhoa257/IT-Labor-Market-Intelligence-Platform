"""Create the Database V1 system and ingestion foundation.

This is the explicit production baseline for the pre-production repository.  The
former metadata-driven Phase 3 prototype revision is intentionally not an
ancestor of this chain; see docs/DATABASE_V1_FOUNDATION.md.
"""

from alembic import op

revision = "20260726_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE SCHEMA IF NOT EXISTS system")
    op.execute("CREATE SCHEMA IF NOT EXISTS ingestion")
    op.execute("REVOKE ALL ON SCHEMA system FROM PUBLIC")
    op.execute("REVOKE ALL ON SCHEMA ingestion FROM PUBLIC")

    op.execute("""
        CREATE TABLE system.pipeline_versions (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            component VARCHAR(50) NOT NULL,
            version VARCHAR(100) NOT NULL,
            git_commit_sha VARCHAR(64),
            configuration_hash VARCHAR(128),
            metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            released_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_pipeline_versions PRIMARY KEY (id),
            CONSTRAINT uq_pipeline_versions__component_version UNIQUE (component, version),
            CONSTRAINT ck_pipeline_versions__component CHECK (component IN
                ('crawler','discovery','fetcher','extractor','normalizer','validator',
                 'deduplicator','quality','analytics','serving','other')),
            CONSTRAINT ck_pipeline_versions__version_not_blank CHECK (length(trim(version)) > 0),
            CONSTRAINT ck_pipeline_versions__git_commit_sha CHECK
                (git_commit_sha IS NULL OR git_commit_sha ~ '^[0-9a-fA-F]{7,64}$')
        )
    """)
    op.execute("""
        CREATE INDEX ix_pipeline_versions__component_created_at
        ON system.pipeline_versions (component, created_at DESC)
    """)

    op.execute("""
        CREATE TABLE system.background_jobs (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            job_name VARCHAR(150) NOT NULL,
            job_type VARCHAR(50) NOT NULL,
            status VARCHAR(30) DEFAULT 'pending' NOT NULL,
            scheduled_for TIMESTAMPTZ,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            attempt_count INTEGER DEFAULT 0 NOT NULL,
            max_attempts INTEGER DEFAULT 1 NOT NULL,
            payload_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            result_json JSONB,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_background_jobs PRIMARY KEY (id),
            CONSTRAINT ck_background_jobs__job_type CHECK (job_type IN
                ('retention','archive','aggregate_refresh','materialized_view_refresh',
                 'backfill','data_quality','maintenance','other')),
            CONSTRAINT ck_background_jobs__status CHECK (status IN
                ('pending','running','succeeded','failed','cancelled','skipped')),
            CONSTRAINT ck_background_jobs__attempts CHECK
                (attempt_count >= 0 AND max_attempts >= 1 AND attempt_count <= max_attempts),
            CONSTRAINT ck_background_jobs__timestamps CHECK
                (finished_at IS NULL OR (started_at IS NOT NULL AND finished_at >= started_at))
        )
    """)
    op.execute(
        "CREATE INDEX ix_background_jobs__status_scheduled_for ON system.background_jobs (status, scheduled_for)"
    )
    op.execute(
        "CREATE INDEX ix_background_jobs__job_name_created_at ON system.background_jobs (job_name, created_at DESC)"
    )

    op.execute("""
        CREATE TABLE system.audit_events (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            actor_type VARCHAR(30) NOT NULL,
            actor_id VARCHAR(255),
            action VARCHAR(100) NOT NULL,
            entity_schema VARCHAR(63),
            entity_table VARCHAR(63),
            entity_id VARCHAR(255),
            request_id VARCHAR(100),
            before_json JSONB,
            after_json JSONB,
            metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_audit_events PRIMARY KEY (id),
            CONSTRAINT ck_audit_events__actor_type CHECK
                (actor_type IN ('user','service','system','migration','unknown')),
            CONSTRAINT ck_audit_events__action_not_blank CHECK (length(trim(action)) > 0)
        )
    """)
    op.execute("CREATE INDEX ix_audit_events__created_at ON system.audit_events (created_at DESC)")
    op.execute(
        "CREATE INDEX ix_audit_events__entity ON system.audit_events (entity_schema, entity_table, entity_id)"
    )
    op.execute(
        "CREATE INDEX ix_audit_events__request_id ON system.audit_events (request_id) WHERE request_id IS NOT NULL"
    )

    op.execute("""
        CREATE TABLE ingestion.sources (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            slug VARCHAR(100) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            base_url TEXT NOT NULL,
            source_type VARCHAR(50) DEFAULT 'job_board' NOT NULL,
            country_code CHAR(2),
            status VARCHAR(30) DEFAULT 'researching' NOT NULL,
            is_enabled BOOLEAN DEFAULT false NOT NULL,
            owner_contact VARCHAR(255),
            metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_sources PRIMARY KEY (id),
            CONSTRAINT uq_sources__slug UNIQUE (slug),
            CONSTRAINT ck_sources__slug CHECK
                (slug ~ '^[a-z0-9]+(?:[a-z0-9_-]*[a-z0-9])?$'),
            CONSTRAINT ck_sources__display_name_not_blank CHECK (length(trim(display_name)) > 0),
            CONSTRAINT ck_sources__base_url CHECK (base_url ~ '^https?://'),
            CONSTRAINT ck_sources__source_type CHECK (source_type IN
                ('job_board','company_career_site','aggregator','government','community','other')),
            CONSTRAINT ck_sources__country_code CHECK
                (country_code IS NULL OR country_code ~ '^[A-Z]{2}$'),
            CONSTRAINT ck_sources__status CHECK
                (status IN ('researching','approved','paused','blocked','retired')),
            CONSTRAINT ck_sources__enabled_only_when_approved CHECK
                (NOT is_enabled OR status = 'approved')
        )
    """)
    op.execute("CREATE INDEX ix_sources__status_enabled ON ingestion.sources (status, is_enabled)")
    op.execute("CREATE INDEX ix_sources__source_type ON ingestion.sources (source_type)")

    op.execute("""
        CREATE TABLE system.retention_policies (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            source_id UUID,
            data_class VARCHAR(50) NOT NULL,
            retention_days INTEGER,
            action VARCHAR(30) DEFAULT 'delete' NOT NULL,
            is_active BOOLEAN DEFAULT true NOT NULL,
            policy_version VARCHAR(100) NOT NULL,
            notes TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_retention_policies PRIMARY KEY (id),
            CONSTRAINT fk_retention_policies__source_id__sources FOREIGN KEY (source_id)
                REFERENCES ingestion.sources(id) ON DELETE CASCADE,
            CONSTRAINT ck_retention_policies__data_class CHECK (data_class IN
                ('raw_html','raw_json','structured_evidence','failed_response_body',
                 'fetch_metadata','extracted_record','crawl_error','audit_event','other')),
            CONSTRAINT ck_retention_policies__action CHECK
                (action IN ('delete','archive','redact','retain')),
            CONSTRAINT ck_retention_policies__retention_days CHECK
                (retention_days IS NULL OR retention_days >= 0),
            CONSTRAINT ck_retention_policies__policy_version_not_blank CHECK
                (length(trim(policy_version)) > 0)
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX uq_retention_policies__global_data_class_version ON system.retention_policies (data_class, policy_version) WHERE source_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_retention_policies__source_data_class_version ON system.retention_policies (source_id, data_class, policy_version) WHERE source_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_retention_policies__source_id ON system.retention_policies (source_id)"
    )
    op.execute(
        "CREATE INDEX ix_retention_policies__active_data_class ON system.retention_policies (data_class, is_active)"
    )

    op.execute("""
        CREATE TABLE ingestion.source_policies (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            source_id UUID NOT NULL,
            policy_version VARCHAR(100) NOT NULL,
            robots_review_status VARCHAR(30) DEFAULT 'not_reviewed' NOT NULL,
            terms_review_status VARCHAR(30) DEFAULT 'not_reviewed' NOT NULL,
            approved_paths JSONB DEFAULT '[]'::jsonb NOT NULL,
            blocked_paths JSONB DEFAULT '[]'::jsonb NOT NULL,
            minimum_request_interval_seconds NUMERIC(10,3) DEFAULT 2.000 NOT NULL,
            maximum_requests_per_run INTEGER DEFAULT 30 NOT NULL,
            maximum_concurrent_requests INTEGER DEFAULT 1 NOT NULL,
            raw_retention_days INTEGER DEFAULT 30,
            description_retention_days INTEGER DEFAULT 90,
            allow_raw_storage BOOLEAN DEFAULT true NOT NULL,
            allow_description_storage BOOLEAN DEFAULT true NOT NULL,
            notes TEXT,
            reviewed_by VARCHAR(255),
            reviewed_at TIMESTAMPTZ,
            valid_from TIMESTAMPTZ DEFAULT now() NOT NULL,
            valid_to TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_source_policies PRIMARY KEY (id),
            CONSTRAINT fk_source_policies__source_id__sources FOREIGN KEY (source_id)
                REFERENCES ingestion.sources(id) ON DELETE CASCADE,
            CONSTRAINT uq_source_policies__source_id_policy_version UNIQUE (source_id, policy_version),
            CONSTRAINT ck_source_policies__robots_review_status CHECK (robots_review_status IN
                ('not_reviewed','approved','restricted','rejected','needs_update')),
            CONSTRAINT ck_source_policies__terms_review_status CHECK (terms_review_status IN
                ('not_reviewed','approved','restricted','rejected','needs_update')),
            CONSTRAINT ck_source_policies__approved_paths_array CHECK (jsonb_typeof(approved_paths) = 'array'),
            CONSTRAINT ck_source_policies__blocked_paths_array CHECK (jsonb_typeof(blocked_paths) = 'array'),
            CONSTRAINT ck_source_policies__limits CHECK
                (minimum_request_interval_seconds >= 0 AND maximum_requests_per_run >= 1
                 AND maximum_concurrent_requests >= 1),
            CONSTRAINT ck_source_policies__retention_days CHECK
                ((raw_retention_days IS NULL OR raw_retention_days >= 0)
                 AND (description_retention_days IS NULL OR description_retention_days >= 0)),
            CONSTRAINT ck_source_policies__validity CHECK (valid_to IS NULL OR valid_to > valid_from),
            CONSTRAINT ck_source_policies__reviewer CHECK (reviewed_at IS NULL OR reviewed_by IS NOT NULL)
        )
    """)
    op.execute(
        "CREATE INDEX ix_source_policies__source_id_valid_from ON ingestion.source_policies (source_id, valid_from DESC)"
    )
    op.execute(
        "CREATE INDEX ix_source_policies__active ON ingestion.source_policies (source_id, valid_from, valid_to)"
    )

    op.execute("""
        CREATE TABLE ingestion.parser_versions (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            source_id UUID NOT NULL,
            pipeline_version_id UUID,
            parser_name VARCHAR(150) NOT NULL,
            version VARCHAR(100) NOT NULL,
            schema_version VARCHAR(100) NOT NULL,
            git_commit_sha VARCHAR(64),
            configuration_hash VARCHAR(128),
            is_active BOOLEAN DEFAULT false NOT NULL,
            metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            retired_at TIMESTAMPTZ,
            CONSTRAINT pk_parser_versions PRIMARY KEY (id),
            CONSTRAINT fk_parser_versions__source_id__sources FOREIGN KEY (source_id)
                REFERENCES ingestion.sources(id) ON DELETE CASCADE,
            CONSTRAINT fk_parser_versions__pipeline_version_id__pipeline_versions
                FOREIGN KEY (pipeline_version_id) REFERENCES system.pipeline_versions(id) ON DELETE SET NULL,
            CONSTRAINT uq_parser_versions__source_parser_version UNIQUE (source_id, parser_name, version),
            CONSTRAINT ck_parser_versions__names_not_blank CHECK
                (length(trim(parser_name)) > 0 AND length(trim(version)) > 0
                 AND length(trim(schema_version)) > 0),
            CONSTRAINT ck_parser_versions__git_commit_sha CHECK
                (git_commit_sha IS NULL OR git_commit_sha ~ '^[0-9a-fA-F]{7,64}$'),
            CONSTRAINT ck_parser_versions__retired_at CHECK
                (retired_at IS NULL OR retired_at >= created_at),
            CONSTRAINT ck_parser_versions__active_not_retired CHECK (NOT is_active OR retired_at IS NULL)
        )
    """)
    op.execute(
        "CREATE INDEX ix_parser_versions__source_id_active ON ingestion.parser_versions (source_id, is_active)"
    )
    op.execute(
        "CREATE INDEX ix_parser_versions__pipeline_version_id ON ingestion.parser_versions (pipeline_version_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_parser_versions__one_active_parser ON ingestion.parser_versions (source_id, parser_name) WHERE is_active"
    )


def downgrade() -> None:
    op.execute("DROP TABLE ingestion.parser_versions")
    op.execute("DROP TABLE ingestion.source_policies")
    op.execute("DROP TABLE system.retention_policies")
    op.execute("DROP TABLE ingestion.sources")
    op.execute("DROP TABLE system.audit_events")
    op.execute("DROP TABLE system.background_jobs")
    op.execute("DROP TABLE system.pipeline_versions")
    op.execute("DROP SCHEMA ingestion")
    op.execute("DROP SCHEMA system")
