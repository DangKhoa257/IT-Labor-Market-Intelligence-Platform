"""Create Database V1 immutable history and data-quality schemas."""

from alembic import op

revision = "20260727_0004"
down_revision = "20260726_0003"
branch_labels = None
depends_on = None


APPEND_ONLY_TABLES = (
    ("history", "job_observations"),
    ("history", "observation_descriptions"),
    ("history", "observation_locations"),
    ("history", "observation_salaries"),
    ("history", "observation_skills"),
    ("history", "observation_occupations"),
    ("history", "job_status_events"),
    ("history", "job_change_events"),
    ("history", "job_repost_events"),
    ("quality", "field_evidence"),
    ("quality", "duplicate_candidates"),
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS history")
    op.execute("CREATE SCHEMA IF NOT EXISTS quality")
    op.execute("REVOKE ALL ON SCHEMA history FROM PUBLIC")
    op.execute("REVOKE ALL ON SCHEMA quality FROM PUBLIC")
    op.execute(
        "ALTER TABLE core.job_postings "
        "ADD CONSTRAINT uq_job_postings__id_source_identity "
        "UNIQUE (id, source_id, source_job_id)"
    )
    op.execute(
        """
        CREATE FUNCTION history.prevent_append_only_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME
                USING ERRCODE = '23514';
        END;
        $$
        """
    )

    op.execute(
        """
        CREATE TABLE history.job_observations (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            job_posting_id UUID NOT NULL,
            source_id UUID NOT NULL,
            source_job_id VARCHAR(255) NOT NULL,
            extracted_record_id BIGINT NOT NULL,
            crawl_run_id UUID,
            previous_observation_id BIGINT,
            observation_reason VARCHAR(30) NOT NULL,
            observed_at TIMESTAMPTZ NOT NULL,
            canonical_hash CHAR(64) NOT NULL,
            source_content_hash CHAR(64),
            status VARCHAR(20) NOT NULL,
            source_url TEXT NOT NULL,
            canonical_url TEXT,
            title_raw TEXT NOT NULL,
            title_normalized TEXT,
            company_id UUID,
            company_name_raw TEXT,
            location_raw TEXT,
            employment_type_code VARCHAR(30),
            seniority_level_code VARCHAR(30),
            work_mode VARCHAR(30),
            experience_min_years NUMERIC(6,2),
            experience_max_years NUMERIC(6,2),
            posted_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            canonical_payload_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            extractor_version VARCHAR(100),
            normalization_version VARCHAR(100) NOT NULL,
            confidence_score NUMERIC(5,4),
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_job_observations PRIMARY KEY (id),
            CONSTRAINT uq_job_observations__id_job UNIQUE (id, job_posting_id),
            CONSTRAINT uq_job_observations__id_extracted UNIQUE (id, extracted_record_id),
            CONSTRAINT uq_job_observations__job_extracted_normalization
                UNIQUE (job_posting_id, extracted_record_id, normalization_version),
            CONSTRAINT fk_job_observations__job_source_identity__job_postings
                FOREIGN KEY (job_posting_id, source_id, source_job_id)
                REFERENCES core.job_postings(id, source_id, source_job_id) ON DELETE RESTRICT,
            CONSTRAINT fk_job_observations__extracted_identity__extracted_records
                FOREIGN KEY (extracted_record_id, source_id, source_job_id)
                REFERENCES ingestion.extracted_records(id, source_id, source_job_id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_observations__crawl_run_id__crawl_runs
                FOREIGN KEY (crawl_run_id) REFERENCES ingestion.crawl_runs(id) ON DELETE SET NULL,
            CONSTRAINT fk_job_observations__previous_job__job_observations
                FOREIGN KEY (previous_observation_id, job_posting_id)
                REFERENCES history.job_observations(id, job_posting_id) ON DELETE RESTRICT,
            CONSTRAINT fk_job_observations__company_id__companies
                FOREIGN KEY (company_id) REFERENCES core.companies(id) ON DELETE RESTRICT,
            CONSTRAINT fk_job_observations__employment_type__employment_types
                FOREIGN KEY (employment_type_code) REFERENCES taxonomy.employment_types(code)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_observations__seniority_level__seniority_levels
                FOREIGN KEY (seniority_level_code) REFERENCES taxonomy.seniority_levels(code)
                ON DELETE RESTRICT,
            CONSTRAINT ck_job_observations__reason CHECK (observation_reason IN
                ('first_seen','content_changed','status_changed','reprocessed',
                 'manual_correction','backfill','other')),
            CONSTRAINT ck_job_observations__status CHECK
                (status IN ('active','expired','closed','removed','unknown')),
            CONSTRAINT ck_job_observations__work_mode CHECK
                (work_mode IS NULL OR work_mode IN
                    ('onsite','hybrid','remote','flexible','unknown')),
            CONSTRAINT ck_job_observations__required_text CHECK
                (length(trim(source_job_id)) > 0 AND length(trim(title_raw)) > 0
                 AND length(trim(normalization_version)) > 0),
            CONSTRAINT ck_job_observations__source_url CHECK (source_url ~ '^https?://'),
            CONSTRAINT ck_job_observations__canonical_url CHECK
                (canonical_url IS NULL OR canonical_url ~ '^https?://'),
            CONSTRAINT ck_job_observations__canonical_hash CHECK
                (canonical_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_job_observations__source_content_hash CHECK
                (source_content_hash IS NULL OR source_content_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_job_observations__payload_object CHECK
                (jsonb_typeof(canonical_payload_json) = 'object'),
            CONSTRAINT ck_job_observations__confidence CHECK
                (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1),
            CONSTRAINT ck_job_observations__experience CHECK
                ((experience_min_years IS NULL OR experience_min_years >= 0)
                 AND (experience_max_years IS NULL OR experience_max_years >= 0)
                 AND (experience_min_years IS NULL OR experience_max_years IS NULL
                      OR experience_min_years <= experience_max_years)),
            CONSTRAINT ck_job_observations__posting_dates CHECK
                (expires_at IS NULL OR posted_at IS NULL OR expires_at >= posted_at),
            CONSTRAINT ck_job_observations__previous_not_self CHECK
                (previous_observation_id IS NULL OR previous_observation_id != id)
        )
        """
    )
    op.execute("ALTER TABLE core.job_postings ADD COLUMN current_observation_id BIGINT")
    op.execute(
        """
        ALTER TABLE core.job_postings
        ADD CONSTRAINT fk_job_postings__current_observation__job_observations
        FOREIGN KEY (current_observation_id, id)
        REFERENCES history.job_observations(id, job_posting_id)
        ON DELETE SET NULL (current_observation_id)
        """
    )
    op.execute(
        "CREATE INDEX ix_job_postings__current_observation_id "
        "ON core.job_postings (current_observation_id) "
        "WHERE current_observation_id IS NOT NULL"
    )

    op.execute(
        """
        CREATE TABLE history.observation_descriptions (
            observation_id BIGINT NOT NULL,
            description_text TEXT,
            description_format VARCHAR(20) DEFAULT 'plain' NOT NULL,
            language_code VARCHAR(10),
            content_hash CHAR(64) NOT NULL,
            redaction_status VARCHAR(30) DEFAULT 'not_required' NOT NULL,
            retained_until TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_observation_descriptions PRIMARY KEY (observation_id),
            CONSTRAINT fk_observation_descriptions__observation_id__job_observations
                FOREIGN KEY (observation_id) REFERENCES history.job_observations(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_observation_descriptions__format CHECK
                (description_format IN ('plain','html','markdown')),
            CONSTRAINT ck_observation_descriptions__redaction_status CHECK
                (redaction_status IN ('not_required','pending','redacted','expired','failed')),
            CONSTRAINT ck_observation_descriptions__content_hash CHECK
                (content_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_observation_descriptions__text CHECK
                ((description_text IS NULL AND redaction_status IN ('redacted','expired'))
                 OR (description_text IS NOT NULL AND length(trim(description_text)) > 0))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE history.observation_locations (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            observation_id BIGINT NOT NULL,
            location_id UUID NOT NULL,
            relationship_type VARCHAR(30) DEFAULT 'workplace' NOT NULL,
            is_primary BOOLEAN DEFAULT false NOT NULL,
            is_remote BOOLEAN DEFAULT false NOT NULL,
            remote_scope VARCHAR(30),
            source_text TEXT,
            confidence NUMERIC(5,4),
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_observation_locations PRIMARY KEY (id),
            CONSTRAINT fk_observation_locations__observation_id__job_observations
                FOREIGN KEY (observation_id) REFERENCES history.job_observations(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_observation_locations__location_id__locations
                FOREIGN KEY (location_id) REFERENCES core.locations(id) ON DELETE RESTRICT,
            CONSTRAINT uq_observation_locations__observation_location_relationship
                UNIQUE (observation_id, location_id, relationship_type),
            CONSTRAINT ck_observation_locations__relationship_type CHECK
                (relationship_type IN
                    ('workplace','applicant_eligible','company_office',
                     'relocation_destination','other')),
            CONSTRAINT ck_observation_locations__remote_scope CHECK
                (remote_scope IS NULL OR remote_scope IN
                    ('vietnam','asia','timezone_limited','worldwide','unspecified')),
            CONSTRAINT ck_observation_locations__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_observation_locations__remote_consistency CHECK
                (is_remote = (remote_scope IS NOT NULL))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_observation_locations__one_primary "
        "ON history.observation_locations (observation_id, relationship_type) "
        "WHERE is_primary"
    )
    op.execute(
        """
        CREATE TABLE history.observation_salaries (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            observation_id BIGINT NOT NULL,
            offer_index SMALLINT DEFAULT 0 NOT NULL,
            source_salary_offer_id BIGINT,
            raw_text TEXT,
            amount_min NUMERIC(20,2),
            amount_max NUMERIC(20,2),
            amount_exact NUMERIC(20,2),
            currency CHAR(3),
            period VARCHAR(20),
            compensation_type VARCHAR(30) DEFAULT 'base_salary' NOT NULL,
            tax_basis VARCHAR(20) DEFAULT 'unknown' NOT NULL,
            is_disclosed BOOLEAN DEFAULT false NOT NULL,
            is_negotiable BOOLEAN DEFAULT false NOT NULL,
            is_estimated BOOLEAN DEFAULT false NOT NULL,
            normalized_monthly_min NUMERIC(20,2),
            normalized_monthly_max NUMERIC(20,2),
            normalized_annual_min NUMERIC(20,2),
            normalized_annual_max NUMERIC(20,2),
            fx_rate NUMERIC(20,8),
            fx_rate_date DATE,
            normalization_method VARCHAR(100),
            confidence NUMERIC(5,4),
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_observation_salaries PRIMARY KEY (id),
            CONSTRAINT fk_observation_salaries__observation_id__job_observations
                FOREIGN KEY (observation_id) REFERENCES history.job_observations(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_observation_salaries__source_offer_id__salary_offers
                FOREIGN KEY (source_salary_offer_id) REFERENCES core.salary_offers(id)
                ON DELETE SET NULL,
            CONSTRAINT uq_observation_salaries__observation_offer
                UNIQUE (observation_id, offer_index),
            CONSTRAINT ck_observation_salaries__offer_index CHECK (offer_index >= 0),
            CONSTRAINT ck_observation_salaries__period CHECK
                (period IS NULL OR period IN
                    ('hour','day','week','month','year','project','unknown')),
            CONSTRAINT ck_observation_salaries__compensation_type CHECK
                (compensation_type IN
                    ('base_salary','total_compensation','bonus','commission','equity',
                     'allowance','other')),
            CONSTRAINT ck_observation_salaries__tax_basis CHECK
                (tax_basis IN ('gross','net','unknown')),
            CONSTRAINT ck_observation_salaries__nonnegative_amounts CHECK
                ((amount_min IS NULL OR amount_min >= 0)
                 AND (amount_max IS NULL OR amount_max >= 0)
                 AND (amount_exact IS NULL OR amount_exact >= 0)
                 AND (normalized_monthly_min IS NULL OR normalized_monthly_min >= 0)
                 AND (normalized_monthly_max IS NULL OR normalized_monthly_max >= 0)
                 AND (normalized_annual_min IS NULL OR normalized_annual_min >= 0)
                 AND (normalized_annual_max IS NULL OR normalized_annual_max >= 0)),
            CONSTRAINT ck_observation_salaries__source_range CHECK
                (amount_min IS NULL OR amount_max IS NULL OR amount_min <= amount_max),
            CONSTRAINT ck_observation_salaries__monthly_range CHECK
                (normalized_monthly_min IS NULL OR normalized_monthly_max IS NULL
                 OR normalized_monthly_min <= normalized_monthly_max),
            CONSTRAINT ck_observation_salaries__annual_range CHECK
                (normalized_annual_min IS NULL OR normalized_annual_max IS NULL
                 OR normalized_annual_min <= normalized_annual_max),
            CONSTRAINT ck_observation_salaries__currency CHECK
                (currency IS NULL OR currency ~ '^[A-Z]{3}$'),
            CONSTRAINT ck_observation_salaries__fx_pair CHECK
                ((fx_rate IS NULL) = (fx_rate_date IS NULL)),
            CONSTRAINT ck_observation_salaries__fx_rate CHECK
                (fx_rate IS NULL OR fx_rate > 0),
            CONSTRAINT ck_observation_salaries__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_observation_salaries__undisclosed_amounts CHECK
                (is_disclosed OR is_estimated
                 OR (amount_min IS NULL AND amount_max IS NULL AND amount_exact IS NULL)),
            CONSTRAINT ck_observation_salaries__disclosed_has_amount CHECK
                (NOT is_disclosed OR amount_min IS NOT NULL OR amount_max IS NOT NULL
                 OR amount_exact IS NOT NULL),
            CONSTRAINT ck_observation_salaries__negotiable_undisclosed CHECK
                (NOT (is_negotiable AND NOT is_disclosed)
                 OR (amount_min IS NULL AND amount_max IS NULL AND amount_exact IS NULL))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE history.observation_skills (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            observation_id BIGINT NOT NULL,
            skill_id UUID NOT NULL,
            requirement_type VARCHAR(20) DEFAULT 'mentioned' NOT NULL,
            evidence_text TEXT,
            evidence_section VARCHAR(100),
            extraction_method VARCHAR(100),
            confidence NUMERIC(5,4),
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_observation_skills PRIMARY KEY (id),
            CONSTRAINT fk_observation_skills__observation_id__job_observations
                FOREIGN KEY (observation_id) REFERENCES history.job_observations(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_observation_skills__skill_id__skills
                FOREIGN KEY (skill_id) REFERENCES taxonomy.skills(id) ON DELETE RESTRICT,
            CONSTRAINT uq_observation_skills__observation_skill_requirement
                UNIQUE (observation_id, skill_id, requirement_type),
            CONSTRAINT ck_observation_skills__requirement_type CHECK
                (requirement_type IN ('required','preferred','mentioned','unknown')),
            CONSTRAINT ck_observation_skills__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE history.observation_occupations (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            observation_id BIGINT NOT NULL,
            occupation_id UUID NOT NULL,
            is_primary BOOLEAN DEFAULT false NOT NULL,
            classification_method VARCHAR(100),
            classifier_version VARCHAR(100),
            confidence NUMERIC(5,4),
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_observation_occupations PRIMARY KEY (id),
            CONSTRAINT fk_observation_occupations__observation_id__job_observations
                FOREIGN KEY (observation_id) REFERENCES history.job_observations(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_observation_occupations__occupation_id__occupations
                FOREIGN KEY (occupation_id) REFERENCES taxonomy.occupations(id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_observation_occupations__observation_occupation
                UNIQUE (observation_id, occupation_id),
            CONSTRAINT ck_observation_occupations__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_observation_occupations__one_primary "
        "ON history.observation_occupations (observation_id) WHERE is_primary"
    )

    op.execute(
        """
        CREATE TABLE history.job_status_events (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            job_posting_id UUID NOT NULL,
            observation_id BIGINT,
            from_status VARCHAR(20),
            to_status VARCHAR(20) NOT NULL,
            event_type VARCHAR(40) NOT NULL,
            event_at TIMESTAMPTZ NOT NULL,
            rule_version VARCHAR(100),
            confidence NUMERIC(5,4),
            evidence_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_job_status_events PRIMARY KEY (id),
            CONSTRAINT fk_job_status_events__job_posting_id__job_postings
                FOREIGN KEY (job_posting_id) REFERENCES core.job_postings(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_status_events__observation_job__job_observations
                FOREIGN KEY (observation_id, job_posting_id)
                REFERENCES history.job_observations(id, job_posting_id) ON DELETE RESTRICT,
            CONSTRAINT ck_job_status_events__statuses CHECK
                ((from_status IS NULL OR from_status IN
                    ('active','expired','closed','removed','unknown'))
                 AND to_status IN ('active','expired','closed','removed','unknown')
                 AND (from_status IS NULL OR from_status != to_status)),
            CONSTRAINT ck_job_status_events__event_type CHECK
                (event_type IN
                    ('first_seen','source_marked_active','source_marked_closed','expiry_elapsed',
                     'repeated_not_found','reactivated','manual_correction','backfill','other')),
            CONSTRAINT ck_job_status_events__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_job_status_events__evidence_object CHECK
                (jsonb_typeof(evidence_json) = 'object')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE history.job_change_events (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            job_posting_id UUID NOT NULL,
            from_observation_id BIGINT NOT NULL,
            to_observation_id BIGINT NOT NULL,
            field_path VARCHAR(500) NOT NULL,
            change_type VARCHAR(30) NOT NULL,
            old_value_json JSONB,
            new_value_json JSONB,
            detected_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_job_change_events PRIMARY KEY (id),
            CONSTRAINT fk_job_change_events__job_posting_id__job_postings
                FOREIGN KEY (job_posting_id) REFERENCES core.job_postings(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_change_events__from_observation_job__job_observations
                FOREIGN KEY (from_observation_id, job_posting_id)
                REFERENCES history.job_observations(id, job_posting_id) ON DELETE RESTRICT,
            CONSTRAINT fk_job_change_events__to_observation_job__job_observations
                FOREIGN KEY (to_observation_id, job_posting_id)
                REFERENCES history.job_observations(id, job_posting_id) ON DELETE RESTRICT,
            CONSTRAINT uq_job_change_events__observations_field_type
                UNIQUE (from_observation_id, to_observation_id, field_path, change_type),
            CONSTRAINT ck_job_change_events__observations_differ CHECK
                (from_observation_id != to_observation_id),
            CONSTRAINT ck_job_change_events__field_path CHECK (length(trim(field_path)) > 0),
            CONSTRAINT ck_job_change_events__change_type CHECK
                (change_type IN
                    ('field_added','field_removed','field_changed','status_changed',
                     'reclassified','corrected','other')),
            CONSTRAINT ck_job_change_events__values_differ CHECK
                (old_value_json IS DISTINCT FROM new_value_json)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE history.job_repost_events (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            job_posting_id UUID NOT NULL,
            previous_observation_id BIGINT NOT NULL,
            new_observation_id BIGINT NOT NULL,
            repost_type VARCHAR(30) NOT NULL,
            previous_posted_at TIMESTAMPTZ,
            new_posted_at TIMESTAMPTZ,
            detection_method VARCHAR(100) NOT NULL,
            method_version VARCHAR(100) NOT NULL,
            confidence NUMERIC(5,4),
            evidence_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            detected_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_job_repost_events PRIMARY KEY (id),
            CONSTRAINT fk_job_repost_events__job_posting_id__job_postings
                FOREIGN KEY (job_posting_id) REFERENCES core.job_postings(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_repost_events__previous_job__job_observations
                FOREIGN KEY (previous_observation_id, job_posting_id)
                REFERENCES history.job_observations(id, job_posting_id) ON DELETE RESTRICT,
            CONSTRAINT fk_job_repost_events__new_observation_job__job_observations
                FOREIGN KEY (new_observation_id, job_posting_id)
                REFERENCES history.job_observations(id, job_posting_id) ON DELETE RESTRICT,
            CONSTRAINT uq_job_repost_events__observations_method
                UNIQUE (previous_observation_id, new_observation_id, method_version),
            CONSTRAINT ck_job_repost_events__observations_differ CHECK
                (previous_observation_id != new_observation_id),
            CONSTRAINT ck_job_repost_events__repost_type CHECK
                (repost_type IN
                    ('source_repost','date_refresh','content_refresh','suspected_repost','other')),
            CONSTRAINT ck_job_repost_events__methods CHECK
                (length(trim(detection_method)) > 0 AND length(trim(method_version)) > 0),
            CONSTRAINT ck_job_repost_events__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_job_repost_events__evidence_object CHECK
                (jsonb_typeof(evidence_json) = 'object')
        )
        """
    )

    op.execute(
        """
        CREATE TABLE quality.validation_runs (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            source_id UUID,
            crawl_run_id UUID,
            pipeline_version_id UUID,
            scope_type VARCHAR(30) NOT NULL,
            ruleset_version VARCHAR(100) NOT NULL,
            status VARCHAR(30) DEFAULT 'pending' NOT NULL,
            scope_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            records_checked_count INTEGER DEFAULT 0 NOT NULL,
            issues_found_count INTEGER DEFAULT 0 NOT NULL,
            critical_issue_count INTEGER DEFAULT 0 NOT NULL,
            metrics_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_validation_runs PRIMARY KEY (id),
            CONSTRAINT fk_validation_runs__source_id__sources
                FOREIGN KEY (source_id) REFERENCES ingestion.sources(id) ON DELETE SET NULL,
            CONSTRAINT fk_validation_runs__crawl_run_id__crawl_runs
                FOREIGN KEY (crawl_run_id) REFERENCES ingestion.crawl_runs(id) ON DELETE SET NULL,
            CONSTRAINT fk_validation_runs__pipeline_version_id__pipeline_versions
                FOREIGN KEY (pipeline_version_id) REFERENCES system.pipeline_versions(id)
                ON DELETE SET NULL,
            CONSTRAINT ck_validation_runs__scope_type CHECK
                (scope_type IN
                    ('extracted_record','observation','crawl_run','batch','full_scan','other')),
            CONSTRAINT ck_validation_runs__ruleset_version CHECK
                (length(trim(ruleset_version)) > 0),
            CONSTRAINT ck_validation_runs__status CHECK
                (status IN
                    ('pending','running','succeeded','partially_succeeded','failed','cancelled')),
            CONSTRAINT ck_validation_runs__json_objects CHECK
                (jsonb_typeof(scope_json) = 'object' AND jsonb_typeof(metrics_json) = 'object'),
            CONSTRAINT ck_validation_runs__counters CHECK
                (records_checked_count >= 0 AND issues_found_count >= 0
                 AND critical_issue_count >= 0
                 AND critical_issue_count <= issues_found_count),
            CONSTRAINT ck_validation_runs__timestamps CHECK
                (finished_at IS NULL OR
                    (started_at IS NOT NULL AND finished_at >= started_at)),
            CONSTRAINT ck_validation_runs__running_started CHECK
                (status != 'running' OR started_at IS NOT NULL),
            CONSTRAINT ck_validation_runs__terminal_finished CHECK
                (status NOT IN ('succeeded','partially_succeeded','failed','cancelled')
                 OR finished_at IS NOT NULL)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE quality.data_quality_issues (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            validation_run_id UUID NOT NULL,
            source_id UUID,
            crawl_run_id UUID,
            extracted_record_id BIGINT,
            job_posting_id UUID,
            observation_id BIGINT,
            issue_code VARCHAR(150) NOT NULL,
            field_path VARCHAR(500),
            severity VARCHAR(20) DEFAULT 'warning' NOT NULL,
            status VARCHAR(30) DEFAULT 'open' NOT NULL,
            fingerprint CHAR(64) NOT NULL,
            message TEXT NOT NULL,
            rule_version VARCHAR(100) NOT NULL,
            evidence_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            detected_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            reviewed_by VARCHAR(255),
            reviewed_at TIMESTAMPTZ,
            resolved_at TIMESTAMPTZ,
            resolution_notes TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_data_quality_issues PRIMARY KEY (id),
            CONSTRAINT fk_data_quality_issues__validation_run_id__validation_runs
                FOREIGN KEY (validation_run_id) REFERENCES quality.validation_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_data_quality_issues__source_id__sources
                FOREIGN KEY (source_id) REFERENCES ingestion.sources(id) ON DELETE SET NULL,
            CONSTRAINT fk_data_quality_issues__crawl_run_id__crawl_runs
                FOREIGN KEY (crawl_run_id) REFERENCES ingestion.crawl_runs(id) ON DELETE SET NULL,
            CONSTRAINT fk_data_quality_issues__extracted_record_id__extracted_records
                FOREIGN KEY (extracted_record_id) REFERENCES ingestion.extracted_records(id)
                ON DELETE SET NULL,
            CONSTRAINT fk_data_quality_issues__job_posting_id__job_postings
                FOREIGN KEY (job_posting_id) REFERENCES core.job_postings(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_data_quality_issues__observation_job__job_observations
                FOREIGN KEY (observation_id, job_posting_id)
                REFERENCES history.job_observations(id, job_posting_id) ON DELETE RESTRICT,
            CONSTRAINT uq_data_quality_issues__run_fingerprint
                UNIQUE (validation_run_id, fingerprint),
            CONSTRAINT ck_data_quality_issues__severity CHECK
                (severity IN ('info','warning','error','critical')),
            CONSTRAINT ck_data_quality_issues__status CHECK
                (status IN ('open','acknowledged','resolved','false_positive','suppressed')),
            CONSTRAINT ck_data_quality_issues__fingerprint CHECK
                (fingerprint ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_data_quality_issues__required_text CHECK
                (length(trim(issue_code)) > 0 AND length(trim(message)) > 0
                 AND length(trim(rule_version)) > 0),
            CONSTRAINT ck_data_quality_issues__evidence_object CHECK
                (jsonb_typeof(evidence_json) = 'object'),
            CONSTRAINT ck_data_quality_issues__context CHECK
                (crawl_run_id IS NOT NULL OR extracted_record_id IS NOT NULL
                 OR job_posting_id IS NOT NULL OR observation_id IS NOT NULL),
            CONSTRAINT ck_data_quality_issues__observation_job CHECK
                (observation_id IS NULL OR job_posting_id IS NOT NULL),
            CONSTRAINT ck_data_quality_issues__reviewer CHECK
                (reviewed_at IS NULL OR reviewed_by IS NOT NULL),
            CONSTRAINT ck_data_quality_issues__resolution CHECK
                ((status IN ('resolved','false_positive','suppressed') AND resolved_at IS NOT NULL)
                 OR (status IN ('open','acknowledged') AND resolved_at IS NULL))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE quality.field_evidence (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            observation_id BIGINT NOT NULL,
            field_path VARCHAR(500) NOT NULL,
            evidence_index SMALLINT DEFAULT 0 NOT NULL,
            classification VARCHAR(30) NOT NULL,
            raw_value_json JSONB,
            normalized_value_json JSONB,
            evidence_path TEXT,
            evidence_section VARCHAR(100),
            extraction_method VARCHAR(100),
            extractor_version VARCHAR(100),
            normalization_rule VARCHAR(150),
            normalization_version VARCHAR(100),
            inference_method VARCHAR(150),
            confidence NUMERIC(5,4),
            review_status VARCHAR(30) DEFAULT 'unreviewed' NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_field_evidence PRIMARY KEY (id),
            CONSTRAINT fk_field_evidence__observation_id__job_observations
                FOREIGN KEY (observation_id) REFERENCES history.job_observations(id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_field_evidence__observation_field_index
                UNIQUE (observation_id, field_path, evidence_index),
            CONSTRAINT ck_field_evidence__evidence_index CHECK (evidence_index >= 0),
            CONSTRAINT ck_field_evidence__field_path CHECK (length(trim(field_path)) > 0),
            CONSTRAINT ck_field_evidence__classification CHECK
                (classification IN
                    ('direct_structured','direct_html','description_derived','normalized',
                     'inferred','not_available','unverified')),
            CONSTRAINT ck_field_evidence__review_status CHECK
                (review_status IN ('unreviewed','verified','rejected','needs_review')),
            CONSTRAINT ck_field_evidence__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_field_evidence__availability CHECK
                ((classification = 'not_available'
                  AND raw_value_json IS NULL AND normalized_value_json IS NULL)
                 OR (classification != 'not_available'
                     AND (raw_value_json IS NOT NULL OR normalized_value_json IS NOT NULL
                          OR evidence_path IS NOT NULL OR evidence_section IS NOT NULL
                          OR extraction_method IS NOT NULL OR extractor_version IS NOT NULL
                          OR normalization_rule IS NOT NULL OR normalization_version IS NOT NULL
                          OR inference_method IS NOT NULL))),
            CONSTRAINT ck_field_evidence__inference_method CHECK
                (classification != 'inferred' OR
                    (inference_method IS NOT NULL AND length(trim(inference_method)) > 0)),
            CONSTRAINT ck_field_evidence__normalization_rule CHECK
                (classification != 'normalized' OR
                    (normalization_rule IS NOT NULL
                     AND length(trim(normalization_rule)) > 0
                     AND normalization_version IS NOT NULL
                     AND length(trim(normalization_version)) > 0))
        )
        """
    )
    op.execute(
        """
        CREATE TABLE quality.duplicate_candidates (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            left_job_posting_id UUID NOT NULL,
            right_job_posting_id UUID NOT NULL,
            candidate_reason VARCHAR(50) NOT NULL,
            method_version VARCHAR(100) NOT NULL,
            score NUMERIC(5,4) NOT NULL,
            feature_vector_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_duplicate_candidates PRIMARY KEY (id),
            CONSTRAINT fk_duplicate_candidates__left_job_id__job_postings
                FOREIGN KEY (left_job_posting_id) REFERENCES core.job_postings(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_duplicate_candidates__right_job_id__job_postings
                FOREIGN KEY (right_job_posting_id) REFERENCES core.job_postings(id)
                ON DELETE RESTRICT,
            CONSTRAINT uq_duplicate_candidates__pair_method
                UNIQUE (left_job_posting_id, right_job_posting_id, method_version),
            CONSTRAINT ck_duplicate_candidates__reason CHECK
                (candidate_reason IN
                    ('same_source_url','same_company_title_location','similar_content',
                     'repost_pattern','manual','other')),
            CONSTRAINT ck_duplicate_candidates__pair_order CHECK
                (left_job_posting_id < right_job_posting_id),
            CONSTRAINT ck_duplicate_candidates__score CHECK (score BETWEEN 0 AND 1),
            CONSTRAINT ck_duplicate_candidates__method_version CHECK
                (length(trim(method_version)) > 0),
            CONSTRAINT ck_duplicate_candidates__features_object CHECK
                (jsonb_typeof(feature_vector_json) = 'object')
        )
        """
    )
    op.execute(
        """
        CREATE TABLE quality.duplicate_clusters (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            cluster_type VARCHAR(30) NOT NULL,
            method_version VARCHAR(100) NOT NULL,
            score NUMERIC(5,4),
            review_status VARCHAR(30) DEFAULT 'pending' NOT NULL,
            created_by VARCHAR(20) DEFAULT 'automated' NOT NULL,
            notes TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_duplicate_clusters PRIMARY KEY (id),
            CONSTRAINT ck_duplicate_clusters__cluster_type CHECK
                (cluster_type IN
                    ('exact_duplicate','near_duplicate','repost_series',
                     'possible_duplicate','other')),
            CONSTRAINT ck_duplicate_clusters__review_status CHECK
                (review_status IN ('pending','approved','rejected','needs_review')),
            CONSTRAINT ck_duplicate_clusters__created_by CHECK
                (created_by IN ('automated','manual')),
            CONSTRAINT ck_duplicate_clusters__method_version CHECK
                (length(trim(method_version)) > 0),
            CONSTRAINT ck_duplicate_clusters__score CHECK
                (score IS NULL OR score BETWEEN 0 AND 1)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE quality.duplicate_cluster_members (
            cluster_id UUID NOT NULL,
            job_posting_id UUID NOT NULL,
            member_role VARCHAR(20) DEFAULT 'member' NOT NULL,
            membership_score NUMERIC(5,4),
            added_by VARCHAR(20) DEFAULT 'automated' NOT NULL,
            evidence_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_duplicate_cluster_members
                PRIMARY KEY (cluster_id, job_posting_id),
            CONSTRAINT fk_duplicate_cluster_members__cluster_id__duplicate_clusters
                FOREIGN KEY (cluster_id) REFERENCES quality.duplicate_clusters(id)
                ON DELETE CASCADE,
            CONSTRAINT fk_duplicate_cluster_members__job_posting_id__job_postings
                FOREIGN KEY (job_posting_id) REFERENCES core.job_postings(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_duplicate_cluster_members__member_role CHECK
                (member_role IN ('representative','member')),
            CONSTRAINT ck_duplicate_cluster_members__added_by CHECK
                (added_by IN ('automated','manual')),
            CONSTRAINT ck_duplicate_cluster_members__score CHECK
                (membership_score IS NULL OR membership_score BETWEEN 0 AND 1),
            CONSTRAINT ck_duplicate_cluster_members__evidence_object CHECK
                (jsonb_typeof(evidence_json) = 'object')
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_duplicate_cluster_members__one_representative "
        "ON quality.duplicate_cluster_members (cluster_id) "
        "WHERE member_role = 'representative'"
    )

    for schema, table in APPEND_ONLY_TABLES:
        op.execute(
            f"CREATE TRIGGER trg_{table}__append_only "
            f"BEFORE UPDATE OR DELETE ON {schema}.{table} "
            "FOR EACH ROW EXECUTE FUNCTION history.prevent_append_only_mutation()"
        )

    index_statements = (
        "CREATE INDEX ix_job_observations__job_observed "
        "ON history.job_observations (job_posting_id, observed_at DESC, id DESC)",
        "CREATE INDEX ix_job_observations__source_observed "
        "ON history.job_observations (source_id, observed_at DESC)",
        "CREATE INDEX ix_job_observations__canonical_hash "
        "ON history.job_observations (canonical_hash)",
        "CREATE INDEX ix_job_observations__extracted_record_id "
        "ON history.job_observations (extracted_record_id)",
        "CREATE INDEX ix_job_observations__crawl_run_id "
        "ON history.job_observations (crawl_run_id) WHERE crawl_run_id IS NOT NULL",
        "CREATE INDEX ix_job_observations__status_observed "
        "ON history.job_observations (status, observed_at DESC)",
        "CREATE INDEX ix_job_observations__company_observed "
        "ON history.job_observations (company_id, observed_at DESC) WHERE company_id IS NOT NULL",
        "CREATE INDEX ix_observation_descriptions__content_hash "
        "ON history.observation_descriptions (content_hash)",
        "CREATE INDEX ix_observation_descriptions__retained_until "
        "ON history.observation_descriptions (retained_until) WHERE retained_until IS NOT NULL",
        "CREATE INDEX ix_observation_locations__location_id "
        "ON history.observation_locations (location_id)",
        "CREATE INDEX ix_observation_salaries__observation_id "
        "ON history.observation_salaries (observation_id)",
        "CREATE INDEX ix_observation_skills__skill_id ON history.observation_skills (skill_id)",
        "CREATE INDEX ix_observation_occupations__occupation_id "
        "ON history.observation_occupations (occupation_id)",
        "CREATE INDEX ix_job_status_events__job_event_at "
        "ON history.job_status_events (job_posting_id, event_at DESC)",
        "CREATE INDEX ix_job_change_events__job_detected_at "
        "ON history.job_change_events (job_posting_id, detected_at DESC)",
        "CREATE INDEX ix_job_repost_events__job_detected_at "
        "ON history.job_repost_events (job_posting_id, detected_at DESC)",
        "CREATE INDEX ix_validation_runs__status_created_at "
        "ON quality.validation_runs (status, created_at DESC)",
        "CREATE INDEX ix_data_quality_issues__status_severity "
        "ON quality.data_quality_issues (status, severity)",
        "CREATE INDEX ix_field_evidence__observation_id "
        "ON quality.field_evidence (observation_id)",
        "CREATE INDEX ix_duplicate_candidates__left_job_id "
        "ON quality.duplicate_candidates (left_job_posting_id)",
        "CREATE INDEX ix_duplicate_candidates__right_job_id "
        "ON quality.duplicate_candidates (right_job_posting_id)",
        "CREATE INDEX ix_duplicate_cluster_members__job_posting_id "
        "ON quality.duplicate_cluster_members (job_posting_id)",
    )
    for statement in index_statements:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE quality.duplicate_cluster_members")
    op.execute("DROP TABLE quality.duplicate_clusters")
    op.execute("DROP TABLE quality.duplicate_candidates")
    op.execute("DROP TABLE quality.field_evidence")
    op.execute("DROP TABLE quality.data_quality_issues")
    op.execute("DROP TABLE quality.validation_runs")
    op.execute("DROP TABLE history.job_repost_events")
    op.execute("DROP TABLE history.job_change_events")
    op.execute("DROP TABLE history.job_status_events")
    op.execute("DROP TABLE history.observation_occupations")
    op.execute("DROP TABLE history.observation_skills")
    op.execute("DROP TABLE history.observation_salaries")
    op.execute("DROP TABLE history.observation_locations")
    op.execute("DROP TABLE history.observation_descriptions")
    op.execute(
        "ALTER TABLE core.job_postings "
        "DROP CONSTRAINT fk_job_postings__current_observation__job_observations"
    )
    op.execute("DROP INDEX core.ix_job_postings__current_observation_id")
    op.execute("ALTER TABLE core.job_postings DROP COLUMN current_observation_id")
    op.execute("DROP TABLE history.job_observations")
    op.execute("DROP FUNCTION history.prevent_append_only_mutation()")
    op.execute(
        "ALTER TABLE core.job_postings " "DROP CONSTRAINT uq_job_postings__id_source_identity"
    )
    op.execute("DROP SCHEMA quality")
    op.execute("DROP SCHEMA history")
