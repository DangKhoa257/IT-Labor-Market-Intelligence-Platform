"""Create the private Database V1 analytics warehouse."""

from alembic import op

revision = "20260727_0005"
down_revision = "20260727_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS analytics")
    op.execute("REVOKE ALL ON SCHEMA analytics FROM PUBLIC")

    op.execute(
        """
        CREATE TABLE analytics.refresh_runs (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            run_type VARCHAR(30) NOT NULL,
            status VARCHAR(30) DEFAULT 'pending' NOT NULL,
            calculation_version VARCHAR(100) NOT NULL,
            window_start_date DATE,
            window_end_date DATE,
            watermark_observed_at TIMESTAMPTZ,
            lookback_days INTEGER DEFAULT 7 NOT NULL,
            source_id UUID,
            trigger_type VARCHAR(30) DEFAULT 'manual' NOT NULL,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            fact_rows_inserted BIGINT DEFAULT 0 NOT NULL,
            dimension_rows_inserted BIGINT DEFAULT 0 NOT NULL,
            dimension_rows_updated BIGINT DEFAULT 0 NOT NULL,
            aggregate_rows_upserted BIGINT DEFAULT 0 NOT NULL,
            error_count INTEGER DEFAULT 0 NOT NULL,
            configuration_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            metrics_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_refresh_runs PRIMARY KEY (id),
            CONSTRAINT fk_refresh_runs__source_id__sources
                FOREIGN KEY (source_id) REFERENCES ingestion.sources(id) ON DELETE SET NULL,
            CONSTRAINT ck_refresh_runs__run_type CHECK
                (run_type IN ('incremental','backfill','rebuild','validation','test')),
            CONSTRAINT ck_refresh_runs__status CHECK
                (status IN
                    ('pending','running','succeeded','partially_succeeded','failed','cancelled')),
            CONSTRAINT ck_refresh_runs__trigger_type CHECK
                (trigger_type IN
                    ('manual','scheduler','github_actions','api','system','test')),
            CONSTRAINT ck_refresh_runs__calculation_version CHECK
                (length(trim(calculation_version)) > 0),
            CONSTRAINT ck_refresh_runs__nonnegative CHECK
                (lookback_days >= 0 AND fact_rows_inserted >= 0
                 AND dimension_rows_inserted >= 0 AND dimension_rows_updated >= 0
                 AND aggregate_rows_upserted >= 0 AND error_count >= 0),
            CONSTRAINT ck_refresh_runs__date_window CHECK
                (window_end_date IS NULL OR
                    (window_start_date IS NOT NULL AND window_end_date >= window_start_date)),
            CONSTRAINT ck_refresh_runs__json_objects CHECK
                (jsonb_typeof(configuration_json) = 'object'
                 AND jsonb_typeof(metrics_json) = 'object'),
            CONSTRAINT ck_refresh_runs__timestamps CHECK
                (finished_at IS NULL OR
                    (started_at IS NOT NULL AND finished_at >= started_at)),
            CONSTRAINT ck_refresh_runs__terminal_timestamps CHECK
                (status NOT IN ('succeeded','partially_succeeded','failed','cancelled')
                 OR (started_at IS NOT NULL AND finished_at IS NOT NULL))
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_refresh_runs__status_created_at "
        "ON analytics.refresh_runs (status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_refresh_runs__calculation_created_at "
        "ON analytics.refresh_runs (calculation_version, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_refresh_runs__source_created_at "
        "ON analytics.refresh_runs (source_id, created_at DESC) WHERE source_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_refresh_runs__date_window "
        "ON analytics.refresh_runs (window_start_date, window_end_date)"
    )

    op.execute(
        """
        CREATE TABLE analytics.dim_dates (
            date_key INTEGER NOT NULL,
            calendar_date DATE NOT NULL,
            year SMALLINT NOT NULL,
            quarter SMALLINT NOT NULL,
            month SMALLINT NOT NULL,
            month_name VARCHAR(20) NOT NULL,
            week_of_year SMALLINT NOT NULL,
            day_of_month SMALLINT NOT NULL,
            day_of_week SMALLINT NOT NULL,
            day_name VARCHAR(20) NOT NULL,
            is_weekend BOOLEAN NOT NULL,
            month_start_date DATE NOT NULL,
            month_end_date DATE NOT NULL,
            quarter_start_date DATE NOT NULL,
            quarter_end_date DATE NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_dim_dates PRIMARY KEY (date_key),
            CONSTRAINT uq_dim_dates__calendar_date UNIQUE (calendar_date),
            CONSTRAINT ck_dim_dates__date_key CHECK
                (date_key = to_char(calendar_date, 'YYYYMMDD')::integer),
            CONSTRAINT ck_dim_dates__parts CHECK
                (quarter BETWEEN 1 AND 4 AND month BETWEEN 1 AND 12
                 AND week_of_year BETWEEN 1 AND 53 AND day_of_month BETWEEN 1 AND 31
                 AND day_of_week BETWEEN 1 AND 7)
        )
        """
    )
    op.execute(
        """
        INSERT INTO analytics.dim_dates (
            date_key, calendar_date, year, quarter, month, month_name,
            week_of_year, day_of_month, day_of_week, day_name, is_weekend,
            month_start_date, month_end_date, quarter_start_date, quarter_end_date
        )
        SELECT
            to_char(day_value, 'YYYYMMDD')::integer,
            day_value,
            extract(year FROM day_value)::smallint,
            extract(quarter FROM day_value)::smallint,
            extract(month FROM day_value)::smallint,
            trim(to_char(day_value, 'Month')),
            extract(week FROM day_value)::smallint,
            extract(day FROM day_value)::smallint,
            extract(isodow FROM day_value)::smallint,
            trim(to_char(day_value, 'Day')),
            extract(isodow FROM day_value) IN (6, 7),
            date_trunc('month', day_value)::date,
            (date_trunc('month', day_value) + interval '1 month - 1 day')::date,
            date_trunc('quarter', day_value)::date,
            (date_trunc('quarter', day_value) + interval '3 months - 1 day')::date
        FROM generate_series(
            '2020-01-01'::date,
            '2035-12-31'::date,
            interval '1 day'
        ) AS generated(day_value)
        """
    )

    op.execute(
        """
        CREATE TABLE analytics.dim_sources (
            source_key BIGINT GENERATED ALWAYS AS IDENTITY,
            source_id UUID NOT NULL,
            slug VARCHAR(100) NOT NULL,
            display_name VARCHAR(255) NOT NULL,
            source_type VARCHAR(50) NOT NULL,
            country_code CHAR(2),
            status VARCHAR(30) NOT NULL,
            is_enabled BOOLEAN NOT NULL,
            source_updated_at TIMESTAMPTZ NOT NULL,
            warehouse_synced_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_dim_sources PRIMARY KEY (source_key),
            CONSTRAINT uq_dim_sources__source_id UNIQUE (source_id),
            CONSTRAINT uq_dim_sources__slug UNIQUE (slug),
            CONSTRAINT fk_dim_sources__source_id__sources
                FOREIGN KEY (source_id) REFERENCES ingestion.sources(id) ON DELETE RESTRICT
        )
        """
    )
    op.execute("CREATE INDEX ix_dim_sources__source_type ON analytics.dim_sources (source_type)")
    op.execute(
        "CREATE INDEX ix_dim_sources__status_enabled "
        "ON analytics.dim_sources (status, is_enabled)"
    )

    op.execute(
        """
        CREATE TABLE analytics.dim_companies (
            company_key BIGINT GENERATED ALWAYS AS IDENTITY,
            company_id UUID NOT NULL,
            canonical_name VARCHAR(500) NOT NULL,
            normalized_name VARCHAR(500) NOT NULL,
            company_type VARCHAR(30) NOT NULL,
            headquarters_location_id UUID,
            resolution_status VARCHAR(30) NOT NULL,
            company_updated_at TIMESTAMPTZ NOT NULL,
            warehouse_synced_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_dim_companies PRIMARY KEY (company_key),
            CONSTRAINT uq_dim_companies__company_id UNIQUE (company_id),
            CONSTRAINT fk_dim_companies__company_id__companies
                FOREIGN KEY (company_id) REFERENCES core.companies(id) ON DELETE RESTRICT,
            CONSTRAINT fk_dim_companies__headquarters_location_id__locations
                FOREIGN KEY (headquarters_location_id) REFERENCES core.locations(id)
                ON DELETE SET NULL
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_dim_companies__normalized_name "
        "ON analytics.dim_companies (normalized_name)"
    )

    op.execute(
        """
        CREATE TABLE analytics.dim_locations (
            location_key BIGINT GENERATED BY DEFAULT AS IDENTITY,
            location_id UUID,
            resolution_key VARCHAR(750) NOT NULL,
            location_type VARCHAR(30) NOT NULL,
            country_code CHAR(2),
            admin_level_1 VARCHAR(255),
            admin_level_2 VARCHAR(255),
            locality VARCHAR(255),
            canonical_label VARCHAR(750) NOT NULL,
            normalized_label VARCHAR(750) NOT NULL,
            latitude NUMERIC(9,6),
            longitude NUMERIC(9,6),
            location_updated_at TIMESTAMPTZ,
            warehouse_synced_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_dim_locations PRIMARY KEY (location_key),
            CONSTRAINT uq_dim_locations__location_id UNIQUE (location_id),
            CONSTRAINT uq_dim_locations__resolution_key UNIQUE (resolution_key),
            CONSTRAINT fk_dim_locations__location_id__locations
                FOREIGN KEY (location_id) REFERENCES core.locations(id) ON DELETE RESTRICT,
            CONSTRAINT ck_dim_locations__unknown_identity CHECK
                ((location_key = -1 AND location_id IS NULL)
                 OR (location_key > 0 AND location_id IS NOT NULL)),
            CONSTRAINT ck_dim_locations__coordinates CHECK
                ((latitude IS NULL) = (longitude IS NULL)
                 AND (latitude IS NULL OR latitude BETWEEN -90 AND 90)
                 AND (longitude IS NULL OR longitude BETWEEN -180 AND 180))
        )
        """
    )
    op.execute(
        """
        INSERT INTO analytics.dim_locations (
            location_key, location_id, resolution_key, location_type,
            canonical_label, normalized_label
        ) VALUES (-1, NULL, 'unknown', 'unknown', 'Unknown location', 'unknown location')
        """
    )
    op.execute(
        "CREATE INDEX ix_dim_locations__normalized_label "
        "ON analytics.dim_locations (normalized_label)"
    )

    op.execute(
        """
        CREATE TABLE analytics.dim_occupations (
            occupation_key BIGINT GENERATED BY DEFAULT AS IDENTITY,
            occupation_id UUID,
            taxonomy_version_id UUID,
            taxonomy_version VARCHAR(100) NOT NULL,
            canonical_code VARCHAR(100) NOT NULL,
            canonical_name VARCHAR(255) NOT NULL,
            normalized_name VARCHAR(255) NOT NULL,
            parent_occupation_id UUID,
            is_active BOOLEAN NOT NULL,
            occupation_updated_at TIMESTAMPTZ,
            warehouse_synced_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_dim_occupations PRIMARY KEY (occupation_key),
            CONSTRAINT uq_dim_occupations__occupation_id UNIQUE (occupation_id),
            CONSTRAINT fk_dim_occupations__occupation_id__occupations
                FOREIGN KEY (occupation_id) REFERENCES taxonomy.occupations(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_dim_occupations__taxonomy_version_id__taxonomy_versions
                FOREIGN KEY (taxonomy_version_id) REFERENCES taxonomy.taxonomy_versions(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_dim_occupations__parent_occupation_id__occupations
                FOREIGN KEY (parent_occupation_id) REFERENCES taxonomy.occupations(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_dim_occupations__unknown_identity CHECK
                ((occupation_key = -1 AND occupation_id IS NULL
                  AND taxonomy_version_id IS NULL)
                 OR (occupation_key > 0 AND occupation_id IS NOT NULL
                     AND taxonomy_version_id IS NOT NULL))
        )
        """
    )
    op.execute(
        """
        INSERT INTO analytics.dim_occupations (
            occupation_key, occupation_id, taxonomy_version_id, taxonomy_version,
            canonical_code, canonical_name, normalized_name, is_active
        ) VALUES (-1, NULL, NULL, 'unknown', 'unknown', 'Unknown occupation',
                  'unknown occupation', true)
        """
    )
    op.execute(
        "CREATE INDEX ix_dim_occupations__normalized_name "
        "ON analytics.dim_occupations (normalized_name)"
    )
    op.execute(
        "CREATE INDEX ix_dim_occupations__taxonomy_version_id "
        "ON analytics.dim_occupations (taxonomy_version_id)"
    )

    op.execute(
        """
        CREATE TABLE analytics.dim_skills (
            skill_key BIGINT GENERATED ALWAYS AS IDENTITY,
            skill_id UUID NOT NULL,
            taxonomy_version_id UUID NOT NULL,
            taxonomy_version VARCHAR(100) NOT NULL,
            canonical_code VARCHAR(100) NOT NULL,
            canonical_name VARCHAR(255) NOT NULL,
            normalized_name VARCHAR(255) NOT NULL,
            skill_type VARCHAR(30) NOT NULL,
            parent_skill_id UUID,
            is_active BOOLEAN NOT NULL,
            skill_updated_at TIMESTAMPTZ NOT NULL,
            warehouse_synced_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_dim_skills PRIMARY KEY (skill_key),
            CONSTRAINT uq_dim_skills__skill_id UNIQUE (skill_id),
            CONSTRAINT fk_dim_skills__skill_id__skills
                FOREIGN KEY (skill_id) REFERENCES taxonomy.skills(id) ON DELETE RESTRICT,
            CONSTRAINT fk_dim_skills__taxonomy_version_id__taxonomy_versions
                FOREIGN KEY (taxonomy_version_id) REFERENCES taxonomy.taxonomy_versions(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_dim_skills__parent_skill_id__skills
                FOREIGN KEY (parent_skill_id) REFERENCES taxonomy.skills(id) ON DELETE RESTRICT
        )
        """
    )
    op.execute("CREATE INDEX ix_dim_skills__skill_type ON analytics.dim_skills (skill_type)")
    op.execute(
        "CREATE INDEX ix_dim_skills__normalized_name ON analytics.dim_skills (normalized_name)"
    )

    op.execute(
        """
        CREATE TABLE analytics.fact_job_observations (
            job_observation_fact_id BIGINT GENERATED ALWAYS AS IDENTITY,
            observation_id BIGINT NOT NULL,
            job_posting_id UUID NOT NULL,
            source_key BIGINT NOT NULL,
            company_key BIGINT,
            observed_date_key INTEGER NOT NULL,
            posted_date_key INTEGER,
            expires_date_key INTEGER,
            previous_observation_id BIGINT,
            observation_reason VARCHAR(30) NOT NULL,
            status VARCHAR(20) NOT NULL,
            employment_type_code VARCHAR(30),
            seniority_level_code VARCHAR(30),
            work_mode VARCHAR(30),
            experience_min_years NUMERIC(6,2),
            experience_max_years NUMERIC(6,2),
            salary_disclosed BOOLEAN DEFAULT false NOT NULL,
            skill_count INTEGER DEFAULT 0 NOT NULL,
            occupation_count INTEGER DEFAULT 0 NOT NULL,
            location_count INTEGER DEFAULT 0 NOT NULL,
            is_first_observation BOOLEAN DEFAULT false NOT NULL,
            is_status_change BOOLEAN DEFAULT false NOT NULL,
            is_content_change BOOLEAN DEFAULT false NOT NULL,
            canonical_hash CHAR(64) NOT NULL,
            normalization_version VARCHAR(100) NOT NULL,
            refresh_run_id UUID NOT NULL,
            loaded_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_fact_job_observations PRIMARY KEY (job_observation_fact_id),
            CONSTRAINT uq_fact_job_observations__observation_id UNIQUE (observation_id),
            CONSTRAINT fk_fact_job_observations__observation_id__job_observations
                FOREIGN KEY (observation_id) REFERENCES history.job_observations(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_fact_job_observations__job_posting_id__job_postings
                FOREIGN KEY (job_posting_id) REFERENCES core.job_postings(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_fact_job_observations__source_key__dim_sources
                FOREIGN KEY (source_key) REFERENCES analytics.dim_sources(source_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_fact_job_observations__company_key__dim_companies
                FOREIGN KEY (company_key) REFERENCES analytics.dim_companies(company_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_fact_job_observations__observed_date_key__dim_dates
                FOREIGN KEY (observed_date_key) REFERENCES analytics.dim_dates(date_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_fact_job_observations__posted_date_key__dim_dates
                FOREIGN KEY (posted_date_key) REFERENCES analytics.dim_dates(date_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_fact_job_observations__expires_date_key__dim_dates
                FOREIGN KEY (expires_date_key) REFERENCES analytics.dim_dates(date_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_fact_job_observations__refresh_run_id__refresh_runs
                FOREIGN KEY (refresh_run_id) REFERENCES analytics.refresh_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_fact_job_observations__counts CHECK
                (skill_count >= 0 AND occupation_count >= 0 AND location_count >= 0),
            CONSTRAINT ck_fact_job_observations__canonical_hash CHECK
                (canonical_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_fact_job_observations__normalization_version CHECK
                (length(trim(normalization_version)) > 0),
            CONSTRAINT ck_fact_job_observations__first_observation CHECK
                (is_first_observation = (previous_observation_id IS NULL)),
            CONSTRAINT ck_fact_job_observations__experience CHECK
                ((experience_min_years IS NULL OR experience_min_years >= 0)
                 AND (experience_max_years IS NULL OR experience_max_years >= 0)
                 AND (experience_min_years IS NULL OR experience_max_years IS NULL
                      OR experience_min_years <= experience_max_years))
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_fact_job_observations__observed_source "
        "ON analytics.fact_job_observations (observed_date_key, source_key)"
    )
    op.execute(
        "CREATE INDEX ix_fact_job_observations__job_observed "
        "ON analytics.fact_job_observations (job_posting_id, observed_date_key)"
    )
    op.execute(
        "CREATE INDEX ix_fact_job_observations__company_observed "
        "ON analytics.fact_job_observations (company_key, observed_date_key) "
        "WHERE company_key IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_fact_job_observations__status_observed "
        "ON analytics.fact_job_observations (status, observed_date_key)"
    )
    op.execute(
        "CREATE INDEX ix_fact_job_observations__work_mode_observed "
        "ON analytics.fact_job_observations (work_mode, observed_date_key)"
    )
    op.execute(
        "CREATE INDEX ix_fact_job_observations__refresh_run_id "
        "ON analytics.fact_job_observations (refresh_run_id)"
    )

    op.execute(
        """
        CREATE TABLE analytics.fact_salary_observations (
            salary_fact_id BIGINT GENERATED ALWAYS AS IDENTITY,
            observation_salary_id BIGINT NOT NULL,
            observation_id BIGINT NOT NULL,
            job_observation_fact_id BIGINT NOT NULL,
            observed_date_key INTEGER NOT NULL,
            source_key BIGINT NOT NULL,
            company_key BIGINT,
            amount_min NUMERIC(20,2),
            amount_max NUMERIC(20,2),
            amount_exact NUMERIC(20,2),
            currency CHAR(3),
            period VARCHAR(20),
            compensation_type VARCHAR(30) NOT NULL,
            tax_basis VARCHAR(20) NOT NULL,
            is_disclosed BOOLEAN NOT NULL,
            is_negotiable BOOLEAN NOT NULL,
            is_estimated BOOLEAN NOT NULL,
            normalized_monthly_min NUMERIC(20,2),
            normalized_monthly_max NUMERIC(20,2),
            normalized_annual_min NUMERIC(20,2),
            normalized_annual_max NUMERIC(20,2),
            fx_rate NUMERIC(20,8),
            fx_rate_date DATE,
            confidence NUMERIC(5,4),
            refresh_run_id UUID NOT NULL,
            loaded_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_fact_salary_observations PRIMARY KEY (salary_fact_id),
            CONSTRAINT uq_fact_salary_observations__observation_salary_id
                UNIQUE (observation_salary_id),
            CONSTRAINT fk_fact_salary_observations__history_salary
                FOREIGN KEY (observation_salary_id)
                REFERENCES history.observation_salaries(id) ON DELETE RESTRICT,
            CONSTRAINT fk_fact_salary_observations__observation_id__job_observations
                FOREIGN KEY (observation_id) REFERENCES history.job_observations(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_fact_salary_observations__job_fact_id__fact_job_observations
                FOREIGN KEY (job_observation_fact_id)
                REFERENCES analytics.fact_job_observations(job_observation_fact_id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_fact_salary_observations__observed_date_key__dim_dates
                FOREIGN KEY (observed_date_key) REFERENCES analytics.dim_dates(date_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_fact_salary_observations__source_key__dim_sources
                FOREIGN KEY (source_key) REFERENCES analytics.dim_sources(source_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_fact_salary_observations__company_key__dim_companies
                FOREIGN KEY (company_key) REFERENCES analytics.dim_companies(company_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_fact_salary_observations__refresh_run_id__refresh_runs
                FOREIGN KEY (refresh_run_id) REFERENCES analytics.refresh_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_fact_salary_observations__period CHECK
                (period IS NULL OR period IN
                    ('hour','day','week','month','year','project','unknown')),
            CONSTRAINT ck_fact_salary_observations__compensation_type CHECK
                (compensation_type IN
                    ('base_salary','total_compensation','bonus','commission','equity',
                     'allowance','other')),
            CONSTRAINT ck_fact_salary_observations__tax_basis CHECK
                (tax_basis IN ('gross','net','unknown')),
            CONSTRAINT ck_fact_salary_observations__nonnegative CHECK
                ((amount_min IS NULL OR amount_min >= 0)
                 AND (amount_max IS NULL OR amount_max >= 0)
                 AND (amount_exact IS NULL OR amount_exact >= 0)
                 AND (normalized_monthly_min IS NULL OR normalized_monthly_min >= 0)
                 AND (normalized_monthly_max IS NULL OR normalized_monthly_max >= 0)
                 AND (normalized_annual_min IS NULL OR normalized_annual_min >= 0)
                 AND (normalized_annual_max IS NULL OR normalized_annual_max >= 0)),
            CONSTRAINT ck_fact_salary_observations__ranges CHECK
                ((amount_min IS NULL OR amount_max IS NULL OR amount_min <= amount_max)
                 AND (normalized_monthly_min IS NULL OR normalized_monthly_max IS NULL
                      OR normalized_monthly_min <= normalized_monthly_max)
                 AND (normalized_annual_min IS NULL OR normalized_annual_max IS NULL
                      OR normalized_annual_min <= normalized_annual_max)),
            CONSTRAINT ck_fact_salary_observations__currency CHECK
                (currency IS NULL OR currency ~ '^[A-Z]{3}$'),
            CONSTRAINT ck_fact_salary_observations__fx_pair CHECK
                ((fx_rate IS NULL) = (fx_rate_date IS NULL)),
            CONSTRAINT ck_fact_salary_observations__fx_rate CHECK
                (fx_rate IS NULL OR fx_rate > 0),
            CONSTRAINT ck_fact_salary_observations__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_fact_salary_observations__disclosure CHECK
                ((NOT is_disclosed OR amount_min IS NOT NULL OR amount_max IS NOT NULL
                  OR amount_exact IS NOT NULL)
                 AND (is_disclosed OR is_estimated
                      OR (amount_min IS NULL AND amount_max IS NULL AND amount_exact IS NULL))
                 AND (NOT (is_negotiable AND NOT is_disclosed)
                      OR (amount_min IS NULL AND amount_max IS NULL
                          AND amount_exact IS NULL)))
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_fact_salary_observations__date_source "
        "ON analytics.fact_salary_observations (observed_date_key, source_key)"
    )
    op.execute(
        "CREATE INDEX ix_fact_salary_observations__currency_period_tax "
        "ON analytics.fact_salary_observations (currency, period, tax_basis)"
    )
    op.execute(
        "CREATE INDEX ix_fact_salary_observations__refresh_run_id "
        "ON analytics.fact_salary_observations (refresh_run_id)"
    )

    op.execute(
        """
        CREATE TABLE analytics.bridge_job_observation_locations (
            job_observation_fact_id BIGINT NOT NULL,
            observation_location_id BIGINT NOT NULL,
            location_key BIGINT NOT NULL,
            relationship_type VARCHAR(30) NOT NULL,
            is_primary BOOLEAN NOT NULL,
            is_remote BOOLEAN NOT NULL,
            remote_scope VARCHAR(30),
            confidence NUMERIC(5,4),
            refresh_run_id UUID NOT NULL,
            loaded_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_bridge_job_observation_locations
                PRIMARY KEY (job_observation_fact_id, observation_location_id),
            CONSTRAINT uq_bridge_job_observation_locations__observation_location_id
                UNIQUE (observation_location_id),
            CONSTRAINT fk_bridge_locations__job_fact__fact_job_observations
                FOREIGN KEY (job_observation_fact_id)
                REFERENCES analytics.fact_job_observations(job_observation_fact_id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_bridge_locations__history_location__locations
                FOREIGN KEY (observation_location_id)
                REFERENCES history.observation_locations(id) ON DELETE RESTRICT,
            CONSTRAINT fk_bridge_locations__location_key__dim_locations
                FOREIGN KEY (location_key) REFERENCES analytics.dim_locations(location_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_bridge_locations__refresh_run__refresh_runs
                FOREIGN KEY (refresh_run_id) REFERENCES analytics.refresh_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_bridge_job_observation_locations__remote_consistency CHECK
                (is_remote = (remote_scope IS NOT NULL)),
            CONSTRAINT ck_bridge_job_observation_locations__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_bridge_job_observation_locations__location_key "
        "ON analytics.bridge_job_observation_locations (location_key)"
    )

    op.execute(
        """
        CREATE TABLE analytics.bridge_job_observation_occupations (
            job_observation_fact_id BIGINT NOT NULL,
            observation_occupation_id BIGINT NOT NULL,
            occupation_key BIGINT NOT NULL,
            is_primary BOOLEAN NOT NULL,
            classification_method VARCHAR(100),
            classifier_version VARCHAR(100),
            confidence NUMERIC(5,4),
            refresh_run_id UUID NOT NULL,
            loaded_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_bridge_job_observation_occupations
                PRIMARY KEY (job_observation_fact_id, observation_occupation_id),
            CONSTRAINT uq_bridge_occupations__history_occupation_id
                UNIQUE (observation_occupation_id),
            CONSTRAINT fk_bridge_occupations__job_fact__fact_job_observations
                FOREIGN KEY (job_observation_fact_id)
                REFERENCES analytics.fact_job_observations(job_observation_fact_id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_bridge_occupations__history_occupation__occupations
                FOREIGN KEY (observation_occupation_id)
                REFERENCES history.observation_occupations(id) ON DELETE RESTRICT,
            CONSTRAINT fk_bridge_occupations__occupation_key__dim_occupations
                FOREIGN KEY (occupation_key)
                REFERENCES analytics.dim_occupations(occupation_key) ON DELETE RESTRICT,
            CONSTRAINT fk_bridge_occupations__refresh_run__refresh_runs
                FOREIGN KEY (refresh_run_id) REFERENCES analytics.refresh_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_bridge_job_observation_occupations__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_bridge_job_observation_occupations__one_primary "
        "ON analytics.bridge_job_observation_occupations (job_observation_fact_id) "
        "WHERE is_primary"
    )
    op.execute(
        "CREATE INDEX ix_bridge_job_observation_occupations__occupation_key "
        "ON analytics.bridge_job_observation_occupations (occupation_key)"
    )

    op.execute(
        """
        CREATE TABLE analytics.bridge_job_observation_skills (
            job_observation_fact_id BIGINT NOT NULL,
            observation_skill_id BIGINT NOT NULL,
            skill_key BIGINT NOT NULL,
            requirement_type VARCHAR(20) NOT NULL,
            confidence NUMERIC(5,4),
            refresh_run_id UUID NOT NULL,
            loaded_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_bridge_job_observation_skills
                PRIMARY KEY (job_observation_fact_id, observation_skill_id),
            CONSTRAINT uq_bridge_job_observation_skills__observation_skill_id
                UNIQUE (observation_skill_id),
            CONSTRAINT fk_bridge_skills__job_fact__fact_job_observations
                FOREIGN KEY (job_observation_fact_id)
                REFERENCES analytics.fact_job_observations(job_observation_fact_id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_bridge_job_observation_skills__history_skill_id__skills
                FOREIGN KEY (observation_skill_id)
                REFERENCES history.observation_skills(id) ON DELETE RESTRICT,
            CONSTRAINT fk_bridge_job_observation_skills__skill_key__dim_skills
                FOREIGN KEY (skill_key) REFERENCES analytics.dim_skills(skill_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_bridge_job_observation_skills__refresh_run_id__refresh_runs
                FOREIGN KEY (refresh_run_id) REFERENCES analytics.refresh_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_bridge_job_observation_skills__requirement_type CHECK
                (requirement_type IN ('required','preferred','mentioned','unknown')),
            CONSTRAINT ck_bridge_job_observation_skills__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_bridge_job_observation_skills__skill_key "
        "ON analytics.bridge_job_observation_skills (skill_key)"
    )

    op.execute(
        """
        CREATE TABLE analytics.daily_market_metrics (
            metric_date DATE NOT NULL,
            source_key BIGINT NOT NULL,
            employment_type_code VARCHAR(30) NOT NULL,
            seniority_level_code VARCHAR(30) NOT NULL,
            work_mode VARCHAR(30) NOT NULL,
            active_posting_count BIGINT DEFAULT 0 NOT NULL,
            new_posting_count BIGINT DEFAULT 0 NOT NULL,
            closed_posting_count BIGINT DEFAULT 0 NOT NULL,
            expired_posting_count BIGINT DEFAULT 0 NOT NULL,
            removed_posting_count BIGINT DEFAULT 0 NOT NULL,
            reactivated_posting_count BIGINT DEFAULT 0 NOT NULL,
            content_changed_count BIGINT DEFAULT 0 NOT NULL,
            salary_disclosed_count BIGINT DEFAULT 0 NOT NULL,
            remote_posting_count BIGINT DEFAULT 0 NOT NULL,
            refresh_run_id UUID NOT NULL,
            calculation_version VARCHAR(100) NOT NULL,
            calculated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_daily_market_metrics PRIMARY KEY
                (metric_date, source_key, employment_type_code,
                 seniority_level_code, work_mode),
            CONSTRAINT fk_daily_market_metrics__metric_date__dim_dates
                FOREIGN KEY (metric_date) REFERENCES analytics.dim_dates(calendar_date)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_market_metrics__source_key__dim_sources
                FOREIGN KEY (source_key) REFERENCES analytics.dim_sources(source_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_market_metrics__employment_type__employment_types
                FOREIGN KEY (employment_type_code) REFERENCES taxonomy.employment_types(code)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_market_metrics__seniority_level__seniority_levels
                FOREIGN KEY (seniority_level_code) REFERENCES taxonomy.seniority_levels(code)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_market_metrics__refresh_run_id__refresh_runs
                FOREIGN KEY (refresh_run_id) REFERENCES analytics.refresh_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_daily_market_metrics__work_mode CHECK
                (work_mode IN ('onsite','hybrid','remote','flexible','unknown')),
            CONSTRAINT ck_daily_market_metrics__counts CHECK
                (active_posting_count >= 0 AND new_posting_count >= 0
                 AND closed_posting_count >= 0 AND expired_posting_count >= 0
                 AND removed_posting_count >= 0 AND reactivated_posting_count >= 0
                 AND content_changed_count >= 0 AND salary_disclosed_count >= 0
                 AND remote_posting_count >= 0),
            CONSTRAINT ck_daily_market_metrics__calculation_version CHECK
                (length(trim(calculation_version)) > 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_daily_market_metrics__source_date_desc "
        "ON analytics.daily_market_metrics (source_key, metric_date DESC)"
    )

    op.execute(
        """
        CREATE TABLE analytics.daily_company_hiring (
            metric_date DATE NOT NULL,
            company_key BIGINT NOT NULL,
            source_key BIGINT NOT NULL,
            active_posting_count BIGINT DEFAULT 0 NOT NULL,
            new_posting_count BIGINT DEFAULT 0 NOT NULL,
            closed_posting_count BIGINT DEFAULT 0 NOT NULL,
            unique_occupation_count BIGINT DEFAULT 0 NOT NULL,
            unique_skill_count BIGINT DEFAULT 0 NOT NULL,
            salary_disclosed_count BIGINT DEFAULT 0 NOT NULL,
            remote_posting_count BIGINT DEFAULT 0 NOT NULL,
            refresh_run_id UUID NOT NULL,
            calculation_version VARCHAR(100) NOT NULL,
            calculated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_daily_company_hiring PRIMARY KEY
                (metric_date, company_key, source_key),
            CONSTRAINT fk_daily_company_hiring__metric_date__dim_dates
                FOREIGN KEY (metric_date) REFERENCES analytics.dim_dates(calendar_date)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_company_hiring__company_key__dim_companies
                FOREIGN KEY (company_key) REFERENCES analytics.dim_companies(company_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_company_hiring__source_key__dim_sources
                FOREIGN KEY (source_key) REFERENCES analytics.dim_sources(source_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_company_hiring__refresh_run_id__refresh_runs
                FOREIGN KEY (refresh_run_id) REFERENCES analytics.refresh_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_daily_company_hiring__counts CHECK
                (active_posting_count >= 0 AND new_posting_count >= 0
                 AND closed_posting_count >= 0 AND unique_occupation_count >= 0
                 AND unique_skill_count >= 0 AND salary_disclosed_count >= 0
                 AND remote_posting_count >= 0),
            CONSTRAINT ck_daily_company_hiring__calculation_version CHECK
                (length(trim(calculation_version)) > 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_daily_company_hiring__company_date_desc "
        "ON analytics.daily_company_hiring (company_key, metric_date DESC)"
    )

    op.execute(
        """
        CREATE TABLE analytics.daily_location_demand (
            metric_date DATE NOT NULL,
            location_key BIGINT NOT NULL,
            source_key BIGINT NOT NULL,
            work_mode VARCHAR(30) NOT NULL,
            active_posting_count BIGINT DEFAULT 0 NOT NULL,
            new_posting_count BIGINT DEFAULT 0 NOT NULL,
            closed_posting_count BIGINT DEFAULT 0 NOT NULL,
            salary_disclosed_count BIGINT DEFAULT 0 NOT NULL,
            refresh_run_id UUID NOT NULL,
            calculation_version VARCHAR(100) NOT NULL,
            calculated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_daily_location_demand PRIMARY KEY
                (metric_date, location_key, source_key, work_mode),
            CONSTRAINT fk_daily_location_demand__metric_date__dim_dates
                FOREIGN KEY (metric_date) REFERENCES analytics.dim_dates(calendar_date)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_location_demand__location_key__dim_locations
                FOREIGN KEY (location_key) REFERENCES analytics.dim_locations(location_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_location_demand__source_key__dim_sources
                FOREIGN KEY (source_key) REFERENCES analytics.dim_sources(source_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_location_demand__refresh_run_id__refresh_runs
                FOREIGN KEY (refresh_run_id) REFERENCES analytics.refresh_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_daily_location_demand__work_mode CHECK
                (work_mode IN ('onsite','hybrid','remote','flexible','unknown')),
            CONSTRAINT ck_daily_location_demand__counts CHECK
                (active_posting_count >= 0 AND new_posting_count >= 0
                 AND closed_posting_count >= 0 AND salary_disclosed_count >= 0),
            CONSTRAINT ck_daily_location_demand__calculation_version CHECK
                (length(trim(calculation_version)) > 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_daily_location_demand__location_date_desc "
        "ON analytics.daily_location_demand (location_key, metric_date DESC)"
    )

    op.execute(
        """
        CREATE TABLE analytics.daily_occupation_demand (
            metric_date DATE NOT NULL,
            occupation_key BIGINT NOT NULL,
            source_key BIGINT NOT NULL,
            active_posting_count BIGINT DEFAULT 0 NOT NULL,
            new_posting_count BIGINT DEFAULT 0 NOT NULL,
            closed_posting_count BIGINT DEFAULT 0 NOT NULL,
            salary_disclosed_count BIGINT DEFAULT 0 NOT NULL,
            remote_posting_count BIGINT DEFAULT 0 NOT NULL,
            refresh_run_id UUID NOT NULL,
            calculation_version VARCHAR(100) NOT NULL,
            calculated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_daily_occupation_demand PRIMARY KEY
                (metric_date, occupation_key, source_key),
            CONSTRAINT fk_daily_occupation_demand__metric_date__dim_dates
                FOREIGN KEY (metric_date) REFERENCES analytics.dim_dates(calendar_date)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_occupation_demand__occupation_key__dim_occupations
                FOREIGN KEY (occupation_key)
                REFERENCES analytics.dim_occupations(occupation_key) ON DELETE RESTRICT,
            CONSTRAINT fk_daily_occupation_demand__source_key__dim_sources
                FOREIGN KEY (source_key) REFERENCES analytics.dim_sources(source_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_occupation_demand__refresh_run_id__refresh_runs
                FOREIGN KEY (refresh_run_id) REFERENCES analytics.refresh_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_daily_occupation_demand__counts CHECK
                (active_posting_count >= 0 AND new_posting_count >= 0
                 AND closed_posting_count >= 0 AND salary_disclosed_count >= 0
                 AND remote_posting_count >= 0),
            CONSTRAINT ck_daily_occupation_demand__calculation_version CHECK
                (length(trim(calculation_version)) > 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_daily_occupation_demand__occupation_date_desc "
        "ON analytics.daily_occupation_demand (occupation_key, metric_date DESC)"
    )

    op.execute(
        """
        CREATE TABLE analytics.daily_skill_demand (
            metric_date DATE NOT NULL,
            skill_key BIGINT NOT NULL,
            source_key BIGINT NOT NULL,
            requirement_type VARCHAR(20) NOT NULL,
            active_posting_count BIGINT DEFAULT 0 NOT NULL,
            new_posting_count BIGINT DEFAULT 0 NOT NULL,
            closed_posting_count BIGINT DEFAULT 0 NOT NULL,
            company_count BIGINT DEFAULT 0 NOT NULL,
            occupation_count BIGINT DEFAULT 0 NOT NULL,
            refresh_run_id UUID NOT NULL,
            calculation_version VARCHAR(100) NOT NULL,
            calculated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_daily_skill_demand PRIMARY KEY
                (metric_date, skill_key, source_key, requirement_type),
            CONSTRAINT fk_daily_skill_demand__metric_date__dim_dates
                FOREIGN KEY (metric_date) REFERENCES analytics.dim_dates(calendar_date)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_skill_demand__skill_key__dim_skills
                FOREIGN KEY (skill_key) REFERENCES analytics.dim_skills(skill_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_skill_demand__source_key__dim_sources
                FOREIGN KEY (source_key) REFERENCES analytics.dim_sources(source_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_skill_demand__refresh_run_id__refresh_runs
                FOREIGN KEY (refresh_run_id) REFERENCES analytics.refresh_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_daily_skill_demand__requirement_type CHECK
                (requirement_type IN ('required','preferred','mentioned','unknown')),
            CONSTRAINT ck_daily_skill_demand__counts CHECK
                (active_posting_count >= 0 AND new_posting_count >= 0
                 AND closed_posting_count >= 0 AND company_count >= 0
                 AND occupation_count >= 0),
            CONSTRAINT ck_daily_skill_demand__calculation_version CHECK
                (length(trim(calculation_version)) > 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_daily_skill_demand__skill_date_desc "
        "ON analytics.daily_skill_demand (skill_key, metric_date DESC)"
    )

    op.execute(
        """
        CREATE TABLE analytics.daily_salary_metrics (
            metric_date DATE NOT NULL,
            source_key BIGINT NOT NULL,
            occupation_key BIGINT NOT NULL,
            location_key BIGINT NOT NULL,
            currency CHAR(3) NOT NULL,
            period VARCHAR(20) NOT NULL,
            tax_basis VARCHAR(20) NOT NULL,
            disclosed_salary_count BIGINT NOT NULL,
            estimated_salary_count BIGINT DEFAULT 0 NOT NULL,
            negotiable_salary_count BIGINT DEFAULT 0 NOT NULL,
            amount_min_average NUMERIC(20,2),
            amount_max_average NUMERIC(20,2),
            amount_exact_average NUMERIC(20,2),
            normalized_monthly_min_average NUMERIC(20,2),
            normalized_monthly_max_average NUMERIC(20,2),
            normalized_annual_min_average NUMERIC(20,2),
            normalized_annual_max_average NUMERIC(20,2),
            normalized_monthly_min_median NUMERIC(20,2),
            normalized_monthly_max_median NUMERIC(20,2),
            normalized_annual_min_median NUMERIC(20,2),
            normalized_annual_max_median NUMERIC(20,2),
            refresh_run_id UUID NOT NULL,
            calculation_version VARCHAR(100) NOT NULL,
            calculated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_daily_salary_metrics PRIMARY KEY
                (metric_date, source_key, occupation_key, location_key,
                 currency, period, tax_basis),
            CONSTRAINT fk_daily_salary_metrics__metric_date__dim_dates
                FOREIGN KEY (metric_date) REFERENCES analytics.dim_dates(calendar_date)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_salary_metrics__source_key__dim_sources
                FOREIGN KEY (source_key) REFERENCES analytics.dim_sources(source_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_salary_metrics__occupation_key__dim_occupations
                FOREIGN KEY (occupation_key)
                REFERENCES analytics.dim_occupations(occupation_key) ON DELETE RESTRICT,
            CONSTRAINT fk_daily_salary_metrics__location_key__dim_locations
                FOREIGN KEY (location_key) REFERENCES analytics.dim_locations(location_key)
                ON DELETE RESTRICT,
            CONSTRAINT fk_daily_salary_metrics__refresh_run_id__refresh_runs
                FOREIGN KEY (refresh_run_id) REFERENCES analytics.refresh_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_daily_salary_metrics__currency CHECK (currency ~ '^[A-Z]{3}$'),
            CONSTRAINT ck_daily_salary_metrics__period CHECK
                (period IN ('hour','day','week','month','year','project','unknown')),
            CONSTRAINT ck_daily_salary_metrics__tax_basis CHECK
                (tax_basis IN ('gross','net','unknown')),
            CONSTRAINT ck_daily_salary_metrics__counts CHECK
                (disclosed_salary_count >= 1 AND estimated_salary_count >= 0
                 AND negotiable_salary_count >= 0),
            CONSTRAINT ck_daily_salary_metrics__nonnegative CHECK
                ((amount_min_average IS NULL OR amount_min_average >= 0)
                 AND (amount_max_average IS NULL OR amount_max_average >= 0)
                 AND (amount_exact_average IS NULL OR amount_exact_average >= 0)
                 AND (normalized_monthly_min_average IS NULL
                      OR normalized_monthly_min_average >= 0)
                 AND (normalized_monthly_max_average IS NULL
                      OR normalized_monthly_max_average >= 0)
                 AND (normalized_annual_min_average IS NULL
                      OR normalized_annual_min_average >= 0)
                 AND (normalized_annual_max_average IS NULL
                      OR normalized_annual_max_average >= 0)
                 AND (normalized_monthly_min_median IS NULL
                      OR normalized_monthly_min_median >= 0)
                 AND (normalized_monthly_max_median IS NULL
                      OR normalized_monthly_max_median >= 0)
                 AND (normalized_annual_min_median IS NULL
                      OR normalized_annual_min_median >= 0)
                 AND (normalized_annual_max_median IS NULL
                      OR normalized_annual_max_median >= 0)),
            CONSTRAINT ck_daily_salary_metrics__calculation_version CHECK
                (length(trim(calculation_version)) > 0)
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_daily_salary_metrics__source_date_desc "
        "ON analytics.daily_salary_metrics (source_key, metric_date DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE analytics.daily_salary_metrics")
    op.execute("DROP TABLE analytics.daily_skill_demand")
    op.execute("DROP TABLE analytics.daily_occupation_demand")
    op.execute("DROP TABLE analytics.daily_location_demand")
    op.execute("DROP TABLE analytics.daily_company_hiring")
    op.execute("DROP TABLE analytics.daily_market_metrics")
    op.execute("DROP TABLE analytics.bridge_job_observation_skills")
    op.execute("DROP TABLE analytics.bridge_job_observation_occupations")
    op.execute("DROP TABLE analytics.bridge_job_observation_locations")
    op.execute("DROP TABLE analytics.fact_salary_observations")
    op.execute("DROP TABLE analytics.fact_job_observations")
    op.execute("DROP TABLE analytics.dim_skills")
    op.execute("DROP TABLE analytics.dim_occupations")
    op.execute("DROP TABLE analytics.dim_locations")
    op.execute("DROP TABLE analytics.dim_companies")
    op.execute("DROP TABLE analytics.dim_sources")
    op.execute("DROP TABLE analytics.dim_dates")
    op.execute("DROP TABLE analytics.refresh_runs")
    op.execute("DROP SCHEMA analytics")
