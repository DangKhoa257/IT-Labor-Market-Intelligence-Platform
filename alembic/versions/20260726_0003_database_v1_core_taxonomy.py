"""Create Database V1 canonical core and versioned taxonomy schemas."""

from alembic import op

revision = "20260726_0003"
down_revision = "20260726_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS taxonomy")
    op.execute("CREATE SCHEMA IF NOT EXISTS core")
    op.execute("REVOKE ALL ON SCHEMA taxonomy FROM PUBLIC")
    op.execute("REVOKE ALL ON SCHEMA core FROM PUBLIC")
    op.execute(
        "ALTER TABLE ingestion.extracted_records "
        "ADD CONSTRAINT uq_extracted_records__id_source_identity "
        "UNIQUE (id, source_id, source_job_id)"
    )

    op.execute(
        """
        CREATE TABLE taxonomy.taxonomy_versions (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            taxonomy_type VARCHAR(30) NOT NULL,
            version VARCHAR(100) NOT NULL,
            status VARCHAR(20) DEFAULT 'draft' NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            source_name VARCHAR(255),
            source_url TEXT,
            license_name VARCHAR(255),
            metadata_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            valid_from TIMESTAMPTZ,
            valid_to TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_taxonomy_versions PRIMARY KEY (id),
            CONSTRAINT uq_taxonomy_versions__type_version UNIQUE (taxonomy_type, version),
            CONSTRAINT ck_taxonomy_versions__type CHECK (taxonomy_type IN ('occupation','skill')),
            CONSTRAINT ck_taxonomy_versions__status CHECK (status IN ('draft','active','retired')),
            CONSTRAINT ck_taxonomy_versions__names CHECK
                (length(trim(version)) > 0 AND length(trim(name)) > 0),
            CONSTRAINT ck_taxonomy_versions__validity CHECK
                ((valid_to IS NULL OR valid_from IS NOT NULL)
                 AND (valid_to IS NULL OR valid_to > valid_from)),
            CONSTRAINT ck_taxonomy_versions__active_valid_from CHECK
                (status != 'active' OR valid_from IS NOT NULL)
        )
        """
    )
    op.execute(
        """
        CREATE FUNCTION taxonomy.enforce_taxonomy_entity_type()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            actual_type VARCHAR(30);
        BEGIN
            SELECT taxonomy_type INTO actual_type
            FROM taxonomy.taxonomy_versions
            WHERE id = NEW.taxonomy_version_id;

            IF actual_type IS DISTINCT FROM TG_ARGV[0] THEN
                RAISE EXCEPTION 'taxonomy version % must have type %',
                    NEW.taxonomy_version_id, TG_ARGV[0]
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION taxonomy.prevent_taxonomy_type_change()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.taxonomy_type IS DISTINCT FROM OLD.taxonomy_type THEN
                RAISE EXCEPTION 'taxonomy_type is immutable after insertion'
                    USING ERRCODE = '23514',
                          CONSTRAINT = 'ck_taxonomy_versions__type_immutable';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_taxonomy_versions__immutable_type
        BEFORE UPDATE OF taxonomy_type ON taxonomy.taxonomy_versions
        FOR EACH ROW EXECUTE FUNCTION taxonomy.prevent_taxonomy_type_change()
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_taxonomy_versions__one_active_type "
        "ON taxonomy.taxonomy_versions (taxonomy_type) WHERE status = 'active'"
    )
    op.execute(
        "CREATE INDEX ix_taxonomy_versions__type_created_at "
        "ON taxonomy.taxonomy_versions (taxonomy_type, created_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE taxonomy.employment_types (
            code VARCHAR(30) NOT NULL,
            display_name VARCHAR(100) NOT NULL,
            sort_order SMALLINT DEFAULT 0 NOT NULL,
            is_active BOOLEAN DEFAULT true NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_employment_types PRIMARY KEY (code),
            CONSTRAINT uq_employment_types__display_name UNIQUE (display_name),
            CONSTRAINT ck_employment_types__code CHECK (code ~ '^[a-z][a-z0-9_]*$'),
            CONSTRAINT ck_employment_types__display_name CHECK (length(trim(display_name)) > 0),
            CONSTRAINT ck_employment_types__sort_order CHECK (sort_order >= 0)
        )
        """
    )
    op.execute(
        """
        INSERT INTO taxonomy.employment_types (code, display_name, sort_order) VALUES
            ('full_time', 'Full-time', 10),
            ('part_time', 'Part-time', 20),
            ('contract', 'Contract', 30),
            ('temporary', 'Temporary', 40),
            ('internship', 'Internship', 50),
            ('freelance', 'Freelance', 60),
            ('other', 'Other', 90),
            ('unknown', 'Unknown', 99)
        """
    )

    op.execute(
        """
        CREATE TABLE taxonomy.seniority_levels (
            code VARCHAR(30) NOT NULL,
            display_name VARCHAR(100) NOT NULL,
            rank_order SMALLINT NOT NULL,
            is_management BOOLEAN DEFAULT false NOT NULL,
            is_active BOOLEAN DEFAULT true NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_seniority_levels PRIMARY KEY (code),
            CONSTRAINT uq_seniority_levels__display_name UNIQUE (display_name),
            CONSTRAINT uq_seniority_levels__rank_order UNIQUE (rank_order),
            CONSTRAINT ck_seniority_levels__code CHECK (code ~ '^[a-z][a-z0-9_]*$'),
            CONSTRAINT ck_seniority_levels__display_name CHECK (length(trim(display_name)) > 0),
            CONSTRAINT ck_seniority_levels__rank_order CHECK (rank_order >= 0)
        )
        """
    )
    op.execute(
        """
        INSERT INTO taxonomy.seniority_levels
            (code, display_name, rank_order, is_management) VALUES
            ('intern', 'Intern', 10, false),
            ('entry', 'Entry level', 20, false),
            ('junior', 'Junior', 30, false),
            ('mid', 'Mid-level', 40, false),
            ('senior', 'Senior', 50, false),
            ('lead', 'Lead', 60, false),
            ('manager', 'Manager', 70, true),
            ('director', 'Director', 80, true),
            ('executive', 'Executive', 90, true),
            ('unknown', 'Unknown', 99, false)
        """
    )

    op.execute(
        """
        CREATE TABLE taxonomy.occupations (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            taxonomy_version_id UUID NOT NULL,
            canonical_code VARCHAR(100) NOT NULL,
            canonical_name VARCHAR(255) NOT NULL,
            normalized_name VARCHAR(255) NOT NULL,
            parent_id UUID,
            description TEXT,
            external_system VARCHAR(100),
            external_id VARCHAR(255),
            is_active BOOLEAN DEFAULT true NOT NULL,
            valid_from TIMESTAMPTZ,
            valid_to TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_occupations PRIMARY KEY (id),
            CONSTRAINT fk_occupations__taxonomy_version_id__taxonomy_versions
                FOREIGN KEY (taxonomy_version_id) REFERENCES taxonomy.taxonomy_versions(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_occupations__parent_id_version__occupations
                FOREIGN KEY (parent_id, taxonomy_version_id)
                REFERENCES taxonomy.occupations(id, taxonomy_version_id) ON DELETE RESTRICT,
            CONSTRAINT uq_occupations__version_code UNIQUE (taxonomy_version_id, canonical_code),
            CONSTRAINT uq_occupations__id_version UNIQUE (id, taxonomy_version_id),
            CONSTRAINT ck_occupations__names CHECK
                (length(trim(canonical_code)) > 0 AND length(trim(canonical_name)) > 0
                 AND length(trim(normalized_name)) > 0),
            CONSTRAINT ck_occupations__validity CHECK
                ((valid_to IS NULL OR valid_from IS NOT NULL)
                 AND (valid_to IS NULL OR valid_to > valid_from)),
            CONSTRAINT ck_occupations__parent_not_self CHECK (parent_id IS NULL OR parent_id != id)
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_occupations__taxonomy_type
        BEFORE INSERT OR UPDATE OF taxonomy_version_id ON taxonomy.occupations
        FOR EACH ROW EXECUTE FUNCTION taxonomy.enforce_taxonomy_entity_type('occupation')
        """
    )
    op.execute(
        "CREATE INDEX ix_occupations__taxonomy_version_id ON taxonomy.occupations (taxonomy_version_id)"
    )
    op.execute("CREATE INDEX ix_occupations__parent_id ON taxonomy.occupations (parent_id)")
    op.execute(
        "CREATE INDEX ix_occupations__normalized_name ON taxonomy.occupations (normalized_name)"
    )
    op.execute(
        "CREATE INDEX ix_occupations__active_name ON taxonomy.occupations (is_active, canonical_name)"
    )

    op.execute(
        """
        CREATE TABLE taxonomy.occupation_aliases (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            occupation_id UUID NOT NULL,
            source_id UUID,
            alias VARCHAR(500) NOT NULL,
            normalized_alias VARCHAR(500) NOT NULL,
            language_code VARCHAR(10),
            confidence NUMERIC(5,4),
            is_verified BOOLEAN DEFAULT false NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_occupation_aliases PRIMARY KEY (id),
            CONSTRAINT fk_occupation_aliases__occupation_id__occupations
                FOREIGN KEY (occupation_id) REFERENCES taxonomy.occupations(id) ON DELETE CASCADE,
            CONSTRAINT fk_occupation_aliases__source_id__sources FOREIGN KEY (source_id)
                REFERENCES ingestion.sources(id) ON DELETE SET NULL,
            CONSTRAINT ck_occupation_aliases__names CHECK
                (length(trim(alias)) > 0 AND length(trim(normalized_alias)) > 0),
            CONSTRAINT ck_occupation_aliases__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_occupation_aliases__global ON taxonomy.occupation_aliases (occupation_id, normalized_alias) WHERE source_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_occupation_aliases__source ON taxonomy.occupation_aliases (occupation_id, source_id, normalized_alias) WHERE source_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_occupation_aliases__normalized_alias ON taxonomy.occupation_aliases (normalized_alias)"
    )
    op.execute(
        "CREATE INDEX ix_occupation_aliases__source_id ON taxonomy.occupation_aliases (source_id)"
    )

    op.execute(
        """
        CREATE TABLE taxonomy.skills (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            taxonomy_version_id UUID NOT NULL,
            canonical_code VARCHAR(100) NOT NULL,
            canonical_name VARCHAR(255) NOT NULL,
            normalized_name VARCHAR(255) NOT NULL,
            skill_type VARCHAR(30) DEFAULT 'other' NOT NULL,
            parent_id UUID,
            description TEXT,
            external_system VARCHAR(100),
            external_id VARCHAR(255),
            is_active BOOLEAN DEFAULT true NOT NULL,
            valid_from TIMESTAMPTZ,
            valid_to TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_skills PRIMARY KEY (id),
            CONSTRAINT fk_skills__taxonomy_version_id__taxonomy_versions
                FOREIGN KEY (taxonomy_version_id) REFERENCES taxonomy.taxonomy_versions(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_skills__parent_id_version__skills
                FOREIGN KEY (parent_id, taxonomy_version_id)
                REFERENCES taxonomy.skills(id, taxonomy_version_id) ON DELETE RESTRICT,
            CONSTRAINT uq_skills__version_code UNIQUE (taxonomy_version_id, canonical_code),
            CONSTRAINT uq_skills__id_version UNIQUE (id, taxonomy_version_id),
            CONSTRAINT ck_skills__names CHECK
                (length(trim(canonical_code)) > 0 AND length(trim(canonical_name)) > 0
                 AND length(trim(normalized_name)) > 0),
            CONSTRAINT ck_skills__type CHECK (skill_type IN
                ('programming_language','framework','library','database','cloud','devops','tool',
                 'platform','methodology','security','data','ai_ml','domain','soft_skill','other')),
            CONSTRAINT ck_skills__validity CHECK
                ((valid_to IS NULL OR valid_from IS NOT NULL)
                 AND (valid_to IS NULL OR valid_to > valid_from)),
            CONSTRAINT ck_skills__parent_not_self CHECK (parent_id IS NULL OR parent_id != id)
        )
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_skills__taxonomy_type
        BEFORE INSERT OR UPDATE OF taxonomy_version_id ON taxonomy.skills
        FOR EACH ROW EXECUTE FUNCTION taxonomy.enforce_taxonomy_entity_type('skill')
        """
    )
    op.execute(
        "CREATE INDEX ix_skills__taxonomy_version_id ON taxonomy.skills (taxonomy_version_id)"
    )
    op.execute("CREATE INDEX ix_skills__parent_id ON taxonomy.skills (parent_id)")
    op.execute("CREATE INDEX ix_skills__normalized_name ON taxonomy.skills (normalized_name)")
    op.execute("CREATE INDEX ix_skills__type_active ON taxonomy.skills (skill_type, is_active)")

    op.execute(
        """
        CREATE TABLE taxonomy.skill_aliases (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            skill_id UUID NOT NULL,
            source_id UUID,
            alias VARCHAR(500) NOT NULL,
            normalized_alias VARCHAR(500) NOT NULL,
            language_code VARCHAR(10),
            confidence NUMERIC(5,4),
            is_verified BOOLEAN DEFAULT false NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_skill_aliases PRIMARY KEY (id),
            CONSTRAINT fk_skill_aliases__skill_id__skills FOREIGN KEY (skill_id)
                REFERENCES taxonomy.skills(id) ON DELETE CASCADE,
            CONSTRAINT fk_skill_aliases__source_id__sources FOREIGN KEY (source_id)
                REFERENCES ingestion.sources(id) ON DELETE SET NULL,
            CONSTRAINT ck_skill_aliases__names CHECK
                (length(trim(alias)) > 0 AND length(trim(normalized_alias)) > 0),
            CONSTRAINT ck_skill_aliases__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_skill_aliases__global ON taxonomy.skill_aliases (skill_id, normalized_alias) WHERE source_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_skill_aliases__source ON taxonomy.skill_aliases (skill_id, source_id, normalized_alias) WHERE source_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_skill_aliases__normalized_alias ON taxonomy.skill_aliases (normalized_alias)"
    )
    op.execute("CREATE INDEX ix_skill_aliases__source_id ON taxonomy.skill_aliases (source_id)")

    op.execute(
        """
        CREATE TABLE core.locations (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            resolution_key VARCHAR(750) NOT NULL,
            location_type VARCHAR(30) NOT NULL,
            country_code CHAR(2),
            admin_level_1 VARCHAR(255),
            admin_level_2 VARCHAR(255),
            locality VARCHAR(255),
            street_address TEXT,
            postal_code VARCHAR(30),
            latitude NUMERIC(9,6),
            longitude NUMERIC(9,6),
            canonical_label VARCHAR(750) NOT NULL,
            normalized_label VARCHAR(750) NOT NULL,
            geocoding_provider VARCHAR(100),
            geocoding_version VARCHAR(100),
            confidence NUMERIC(5,4),
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_locations PRIMARY KEY (id),
            CONSTRAINT uq_locations__resolution_key UNIQUE (resolution_key),
            CONSTRAINT ck_locations__type CHECK (location_type IN
                ('country','region','province','city','district','address','remote_scope','other')),
            CONSTRAINT ck_locations__names CHECK
                (length(trim(resolution_key)) > 0 AND length(trim(canonical_label)) > 0
                 AND length(trim(normalized_label)) > 0),
            CONSTRAINT ck_locations__country_code CHECK
                (country_code IS NULL OR country_code ~ '^[A-Z]{2}$'),
            CONSTRAINT ck_locations__latitude CHECK
                (latitude IS NULL OR latitude BETWEEN -90 AND 90),
            CONSTRAINT ck_locations__longitude CHECK
                (longitude IS NULL OR longitude BETWEEN -180 AND 180),
            CONSTRAINT ck_locations__coordinate_pair CHECK
                ((latitude IS NULL) = (longitude IS NULL)),
            CONSTRAINT ck_locations__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1)
        )
        """
    )
    op.execute("CREATE INDEX ix_locations__normalized_label ON core.locations (normalized_label)")
    op.execute(
        "CREATE INDEX ix_locations__country_admin ON core.locations (country_code, admin_level_1, admin_level_2, locality)"
    )
    op.execute("CREATE INDEX ix_locations__type ON core.locations (location_type)")

    op.execute(
        """
        CREATE TABLE core.companies (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            canonical_name VARCHAR(500) NOT NULL,
            normalized_name VARCHAR(500) NOT NULL,
            legal_name VARCHAR(500),
            company_type VARCHAR(30) DEFAULT 'unknown' NOT NULL,
            headquarters_location_id UUID,
            website_url TEXT,
            employee_count_min INTEGER,
            employee_count_max INTEGER,
            resolution_status VARCHAR(30) DEFAULT 'provisional' NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_companies PRIMARY KEY (id),
            CONSTRAINT fk_companies__headquarters_location_id__locations
                FOREIGN KEY (headquarters_location_id) REFERENCES core.locations(id) ON DELETE SET NULL,
            CONSTRAINT ck_companies__names CHECK
                (length(trim(canonical_name)) > 0 AND length(trim(normalized_name)) > 0),
            CONSTRAINT ck_companies__type CHECK (company_type IN
                ('employer','recruitment_agency','outsourcing','consulting','government',
                 'education','nonprofit','unknown','other')),
            CONSTRAINT ck_companies__resolution_status CHECK
                (resolution_status IN ('unresolved','provisional','verified','merged','retired')),
            CONSTRAINT ck_companies__website_url CHECK
                (website_url IS NULL OR website_url ~ '^https?://'),
            CONSTRAINT ck_companies__employee_counts CHECK
                ((employee_count_min IS NULL OR employee_count_min >= 0)
                 AND (employee_count_max IS NULL OR employee_count_max >= 0)
                 AND (employee_count_min IS NULL OR employee_count_max IS NULL
                      OR employee_count_min <= employee_count_max))
        )
        """
    )
    op.execute("CREATE INDEX ix_companies__normalized_name ON core.companies (normalized_name)")
    op.execute("CREATE INDEX ix_companies__resolution_status ON core.companies (resolution_status)")
    op.execute(
        "CREATE INDEX ix_companies__headquarters_location_id ON core.companies (headquarters_location_id)"
    )

    op.execute(
        """
        CREATE TABLE core.company_aliases (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            company_id UUID NOT NULL,
            source_id UUID,
            extracted_record_id BIGINT,
            alias VARCHAR(500) NOT NULL,
            normalized_alias VARCHAR(500) NOT NULL,
            confidence NUMERIC(5,4),
            is_verified BOOLEAN DEFAULT false NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_company_aliases PRIMARY KEY (id),
            CONSTRAINT fk_company_aliases__company_id__companies FOREIGN KEY (company_id)
                REFERENCES core.companies(id) ON DELETE CASCADE,
            CONSTRAINT fk_company_aliases__source_id__sources FOREIGN KEY (source_id)
                REFERENCES ingestion.sources(id) ON DELETE SET NULL,
            CONSTRAINT fk_company_aliases__extracted_record_id__extracted_records
                FOREIGN KEY (extracted_record_id) REFERENCES ingestion.extracted_records(id)
                ON DELETE SET NULL,
            CONSTRAINT ck_company_aliases__names CHECK
                (length(trim(alias)) > 0 AND length(trim(normalized_alias)) > 0),
            CONSTRAINT ck_company_aliases__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_company_aliases__global ON core.company_aliases (company_id, normalized_alias) WHERE source_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_company_aliases__source ON core.company_aliases (company_id, source_id, normalized_alias) WHERE source_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_company_aliases__normalized_alias ON core.company_aliases (normalized_alias)"
    )
    op.execute("CREATE INDEX ix_company_aliases__source_id ON core.company_aliases (source_id)")
    op.execute(
        "CREATE INDEX ix_company_aliases__extracted_record_id ON core.company_aliases (extracted_record_id)"
    )

    op.execute(
        """
        CREATE TABLE core.company_domains (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            company_id UUID NOT NULL,
            source_id UUID,
            domain VARCHAR(255) NOT NULL,
            domain_type VARCHAR(30) DEFAULT 'corporate' NOT NULL,
            is_verified BOOLEAN DEFAULT false NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_company_domains PRIMARY KEY (id),
            CONSTRAINT fk_company_domains__company_id__companies FOREIGN KEY (company_id)
                REFERENCES core.companies(id) ON DELETE CASCADE,
            CONSTRAINT fk_company_domains__source_id__sources FOREIGN KEY (source_id)
                REFERENCES ingestion.sources(id) ON DELETE SET NULL,
            CONSTRAINT uq_company_domains__company_domain_type
                UNIQUE (company_id, domain, domain_type),
            CONSTRAINT ck_company_domains__type CHECK
                (domain_type IN ('corporate','career','email','social','other')),
            CONSTRAINT ck_company_domains__lowercase CHECK (domain = lower(domain)),
            CONSTRAINT ck_company_domains__format CHECK
                (domain ~ '^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$' AND position('.' in domain) > 0)
        )
        """
    )
    op.execute("CREATE INDEX ix_company_domains__domain ON core.company_domains (domain)")
    op.execute("CREATE INDEX ix_company_domains__source_id ON core.company_domains (source_id)")

    op.execute(
        """
        CREATE TABLE core.job_postings (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            source_id UUID NOT NULL,
            source_job_id VARCHAR(255) NOT NULL,
            latest_extracted_record_id BIGINT,
            company_id UUID,
            source_url TEXT NOT NULL,
            canonical_url TEXT,
            title_raw TEXT NOT NULL,
            title_normalized TEXT,
            company_name_raw TEXT,
            company_name_status VARCHAR(30) DEFAULT 'unverified' NOT NULL,
            location_raw TEXT,
            employment_type_code VARCHAR(30),
            seniority_level_code VARCHAR(30),
            work_mode VARCHAR(30),
            experience_min_years NUMERIC(6,2),
            experience_max_years NUMERIC(6,2),
            current_status VARCHAR(20) DEFAULT 'unknown' NOT NULL,
            posted_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            first_seen_at TIMESTAMPTZ NOT NULL,
            last_seen_at TIMESTAMPTZ NOT NULL,
            last_changed_at TIMESTAMPTZ NOT NULL,
            closed_at TIMESTAMPTZ,
            source_content_hash CHAR(64),
            canonical_hash CHAR(64),
            extractor_version VARCHAR(100),
            normalization_version VARCHAR(100),
            confidence_score NUMERIC(5,4),
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_job_postings PRIMARY KEY (id),
            CONSTRAINT fk_job_postings__source_id__sources FOREIGN KEY (source_id)
                REFERENCES ingestion.sources(id) ON DELETE RESTRICT,
            CONSTRAINT fk_job_postings__latest_extracted_identity__extracted_records
                FOREIGN KEY (latest_extracted_record_id, source_id, source_job_id)
                REFERENCES ingestion.extracted_records(id, source_id, source_job_id)
                ON DELETE SET NULL (latest_extracted_record_id),
            CONSTRAINT fk_job_postings__company_id__companies FOREIGN KEY (company_id)
                REFERENCES core.companies(id) ON DELETE RESTRICT,
            CONSTRAINT fk_job_postings__employment_type_code__employment_types
                FOREIGN KEY (employment_type_code) REFERENCES taxonomy.employment_types(code)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_postings__seniority_level_code__seniority_levels
                FOREIGN KEY (seniority_level_code) REFERENCES taxonomy.seniority_levels(code)
                ON DELETE RESTRICT,
            CONSTRAINT uq_job_postings__source_identity UNIQUE (source_id, source_job_id),
            CONSTRAINT ck_job_postings__identity_title CHECK
                (length(trim(source_job_id)) > 0 AND length(trim(title_raw)) > 0),
            CONSTRAINT ck_job_postings__source_url CHECK (source_url ~ '^https?://'),
            CONSTRAINT ck_job_postings__canonical_url CHECK
                (canonical_url IS NULL OR canonical_url ~ '^https?://'),
            CONSTRAINT ck_job_postings__company_name_status CHECK (company_name_status IN
                ('disclosed','hidden_by_source','absent','parse_error','unverified')),
            CONSTRAINT ck_job_postings__work_mode CHECK
                (work_mode IS NULL OR work_mode IN ('onsite','hybrid','remote','flexible','unknown')),
            CONSTRAINT ck_job_postings__current_status CHECK
                (current_status IN ('active','expired','closed','removed','unknown')),
            CONSTRAINT ck_job_postings__experience CHECK
                ((experience_min_years IS NULL OR experience_min_years >= 0)
                 AND (experience_max_years IS NULL OR experience_max_years >= 0)
                 AND (experience_min_years IS NULL OR experience_max_years IS NULL
                      OR experience_min_years <= experience_max_years)),
            CONSTRAINT ck_job_postings__confidence CHECK
                (confidence_score IS NULL OR confidence_score BETWEEN 0 AND 1),
            CONSTRAINT ck_job_postings__source_content_hash CHECK
                (source_content_hash IS NULL OR source_content_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_job_postings__canonical_hash CHECK
                (canonical_hash IS NULL OR canonical_hash ~ '^[0-9a-f]{64}$'),
            CONSTRAINT ck_job_postings__seen_order CHECK (last_seen_at >= first_seen_at),
            CONSTRAINT ck_job_postings__changed_order CHECK (last_changed_at >= first_seen_at),
            CONSTRAINT ck_job_postings__closed_order CHECK
                (closed_at IS NULL OR closed_at >= first_seen_at),
            CONSTRAINT ck_job_postings__posting_dates CHECK
                (expires_at IS NULL OR posted_at IS NULL OR expires_at >= posted_at)
        )
        """
    )
    op.execute("CREATE INDEX ix_job_postings__company_id ON core.job_postings (company_id)")
    op.execute(
        "CREATE INDEX ix_job_postings__status_last_seen ON core.job_postings (current_status, last_seen_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_job_postings__posted_at ON core.job_postings (posted_at DESC) WHERE posted_at IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_job_postings__employment_type ON core.job_postings (employment_type_code)"
    )
    op.execute(
        "CREATE INDEX ix_job_postings__seniority ON core.job_postings (seniority_level_code)"
    )
    op.execute("CREATE INDEX ix_job_postings__work_mode ON core.job_postings (work_mode)")
    op.execute(
        "CREATE INDEX ix_job_postings__canonical_url ON core.job_postings (canonical_url) WHERE canonical_url IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_job_postings__latest_extracted_record_id ON core.job_postings (latest_extracted_record_id)"
    )

    op.execute(
        """
        CREATE TABLE core.job_posting_descriptions (
            job_posting_id UUID NOT NULL,
            extracted_record_id BIGINT,
            description_text TEXT NOT NULL,
            description_format VARCHAR(20) DEFAULT 'plain' NOT NULL,
            language_code VARCHAR(10),
            content_hash CHAR(64) NOT NULL,
            redaction_status VARCHAR(30) DEFAULT 'not_required' NOT NULL,
            retained_until TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_job_posting_descriptions PRIMARY KEY (job_posting_id),
            CONSTRAINT fk_job_posting_descriptions__job_posting_id__job_postings
                FOREIGN KEY (job_posting_id) REFERENCES core.job_postings(id) ON DELETE CASCADE,
            CONSTRAINT fk_job_posting_descriptions__extracted_record_id__extracted_records
                FOREIGN KEY (extracted_record_id) REFERENCES ingestion.extracted_records(id)
                ON DELETE SET NULL,
            CONSTRAINT ck_job_posting_descriptions__format CHECK
                (description_format IN ('plain','html','markdown')),
            CONSTRAINT ck_job_posting_descriptions__redaction_status CHECK
                (redaction_status IN ('not_required','pending','redacted','failed')),
            CONSTRAINT ck_job_posting_descriptions__text CHECK
                (length(trim(description_text)) > 0),
            CONSTRAINT ck_job_posting_descriptions__content_hash CHECK
                (content_hash ~ '^[0-9a-f]{64}$')
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_job_posting_descriptions__extracted_record_id ON core.job_posting_descriptions (extracted_record_id)"
    )
    op.execute(
        "CREATE INDEX ix_job_posting_descriptions__retained_until ON core.job_posting_descriptions (retained_until) WHERE retained_until IS NOT NULL"
    )

    op.execute(
        """
        CREATE TABLE core.job_posting_locations (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            job_posting_id UUID NOT NULL,
            location_id UUID NOT NULL,
            extracted_record_id BIGINT,
            relationship_type VARCHAR(30) DEFAULT 'workplace' NOT NULL,
            is_primary BOOLEAN DEFAULT false NOT NULL,
            is_remote BOOLEAN DEFAULT false NOT NULL,
            remote_scope VARCHAR(30),
            source_text TEXT,
            confidence NUMERIC(5,4),
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_job_posting_locations PRIMARY KEY (id),
            CONSTRAINT fk_job_posting_locations__job_posting_id__job_postings
                FOREIGN KEY (job_posting_id) REFERENCES core.job_postings(id) ON DELETE CASCADE,
            CONSTRAINT fk_job_posting_locations__location_id__locations FOREIGN KEY (location_id)
                REFERENCES core.locations(id) ON DELETE RESTRICT,
            CONSTRAINT fk_job_posting_locations__extracted_record_id__extracted_records
                FOREIGN KEY (extracted_record_id) REFERENCES ingestion.extracted_records(id)
                ON DELETE SET NULL,
            CONSTRAINT uq_job_posting_locations__job_location_relationship
                UNIQUE (job_posting_id, location_id, relationship_type),
            CONSTRAINT ck_job_posting_locations__relationship_type CHECK (relationship_type IN
                ('workplace','applicant_eligible','company_office','relocation_destination','other')),
            CONSTRAINT ck_job_posting_locations__remote_scope CHECK
                (remote_scope IS NULL OR remote_scope IN
                    ('vietnam','asia','timezone_limited','worldwide','unspecified')),
            CONSTRAINT ck_job_posting_locations__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_job_posting_locations__remote_scope_consistency CHECK
                (is_remote = (remote_scope IS NOT NULL))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_job_posting_locations__one_primary ON core.job_posting_locations (job_posting_id, relationship_type) WHERE is_primary"
    )
    op.execute(
        "CREATE INDEX ix_job_posting_locations__location_id ON core.job_posting_locations (location_id)"
    )
    op.execute(
        "CREATE INDEX ix_job_posting_locations__job_posting_id ON core.job_posting_locations (job_posting_id)"
    )
    op.execute(
        "CREATE INDEX ix_job_posting_locations__remote ON core.job_posting_locations (is_remote, remote_scope)"
    )
    op.execute(
        "CREATE INDEX ix_job_posting_locations__extracted_record_id ON core.job_posting_locations (extracted_record_id)"
    )

    op.execute(
        """
        CREATE TABLE core.salary_offers (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            job_posting_id UUID NOT NULL,
            extracted_record_id BIGINT,
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
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_salary_offers PRIMARY KEY (id),
            CONSTRAINT fk_salary_offers__job_posting_id__job_postings
                FOREIGN KEY (job_posting_id) REFERENCES core.job_postings(id) ON DELETE CASCADE,
            CONSTRAINT fk_salary_offers__extracted_record_id__extracted_records
                FOREIGN KEY (extracted_record_id) REFERENCES ingestion.extracted_records(id)
                ON DELETE SET NULL,
            CONSTRAINT ck_salary_offers__period CHECK
                (period IS NULL OR period IN ('hour','day','week','month','year','project','unknown')),
            CONSTRAINT ck_salary_offers__compensation_type CHECK (compensation_type IN
                ('base_salary','total_compensation','bonus','commission','equity','allowance','other')),
            CONSTRAINT ck_salary_offers__tax_basis CHECK (tax_basis IN ('gross','net','unknown')),
            CONSTRAINT ck_salary_offers__nonnegative_amounts CHECK
                ((amount_min IS NULL OR amount_min >= 0) AND (amount_max IS NULL OR amount_max >= 0)
                 AND (amount_exact IS NULL OR amount_exact >= 0)
                 AND (normalized_monthly_min IS NULL OR normalized_monthly_min >= 0)
                 AND (normalized_monthly_max IS NULL OR normalized_monthly_max >= 0)
                 AND (normalized_annual_min IS NULL OR normalized_annual_min >= 0)
                 AND (normalized_annual_max IS NULL OR normalized_annual_max >= 0)),
            CONSTRAINT ck_salary_offers__source_range CHECK
                (amount_min IS NULL OR amount_max IS NULL OR amount_min <= amount_max),
            CONSTRAINT ck_salary_offers__monthly_range CHECK
                (normalized_monthly_min IS NULL OR normalized_monthly_max IS NULL
                 OR normalized_monthly_min <= normalized_monthly_max),
            CONSTRAINT ck_salary_offers__annual_range CHECK
                (normalized_annual_min IS NULL OR normalized_annual_max IS NULL
                 OR normalized_annual_min <= normalized_annual_max),
            CONSTRAINT ck_salary_offers__currency CHECK
                (currency IS NULL OR currency ~ '^[A-Z]{3}$'),
            CONSTRAINT ck_salary_offers__fx_pair CHECK ((fx_rate IS NULL) = (fx_rate_date IS NULL)),
            CONSTRAINT ck_salary_offers__fx_rate CHECK (fx_rate IS NULL OR fx_rate > 0),
            CONSTRAINT ck_salary_offers__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1),
            CONSTRAINT ck_salary_offers__undisclosed_amounts CHECK
                (is_disclosed OR is_estimated
                 OR (amount_min IS NULL AND amount_max IS NULL AND amount_exact IS NULL)),
            CONSTRAINT ck_salary_offers__disclosed_has_amount CHECK
                (NOT is_disclosed OR amount_min IS NOT NULL OR amount_max IS NOT NULL
                 OR amount_exact IS NOT NULL),
            CONSTRAINT ck_salary_offers__negotiable_undisclosed CHECK
                (NOT (is_negotiable AND NOT is_disclosed)
                 OR (amount_min IS NULL AND amount_max IS NULL AND amount_exact IS NULL))
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_salary_offers__job_posting_id ON core.salary_offers (job_posting_id)"
    )
    op.execute(
        "CREATE INDEX ix_salary_offers__currency_period ON core.salary_offers (currency, period) WHERE currency IS NOT NULL"
    )
    op.execute("CREATE INDEX ix_salary_offers__disclosed ON core.salary_offers (is_disclosed)")
    op.execute(
        "CREATE INDEX ix_salary_offers__normalized_monthly ON core.salary_offers (currency, normalized_monthly_min, normalized_monthly_max) WHERE normalized_monthly_min IS NOT NULL OR normalized_monthly_max IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_salary_offers__extracted_record_id ON core.salary_offers (extracted_record_id)"
    )

    op.execute(
        """
        CREATE TABLE core.job_posting_skills (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            job_posting_id UUID NOT NULL,
            skill_id UUID NOT NULL,
            extracted_record_id BIGINT,
            requirement_type VARCHAR(20) DEFAULT 'mentioned' NOT NULL,
            evidence_text TEXT,
            evidence_section VARCHAR(100),
            extraction_method VARCHAR(100),
            confidence NUMERIC(5,4),
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_job_posting_skills PRIMARY KEY (id),
            CONSTRAINT fk_job_posting_skills__job_posting_id__job_postings
                FOREIGN KEY (job_posting_id) REFERENCES core.job_postings(id) ON DELETE CASCADE,
            CONSTRAINT fk_job_posting_skills__skill_id__skills FOREIGN KEY (skill_id)
                REFERENCES taxonomy.skills(id) ON DELETE RESTRICT,
            CONSTRAINT fk_job_posting_skills__extracted_record_id__extracted_records
                FOREIGN KEY (extracted_record_id) REFERENCES ingestion.extracted_records(id)
                ON DELETE SET NULL,
            CONSTRAINT uq_job_posting_skills__job_skill_requirement
                UNIQUE (job_posting_id, skill_id, requirement_type),
            CONSTRAINT ck_job_posting_skills__requirement_type CHECK
                (requirement_type IN ('required','preferred','mentioned','unknown')),
            CONSTRAINT ck_job_posting_skills__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1)
        )
        """
    )
    op.execute("CREATE INDEX ix_job_posting_skills__skill_id ON core.job_posting_skills (skill_id)")
    op.execute(
        "CREATE INDEX ix_job_posting_skills__job_posting_id ON core.job_posting_skills (job_posting_id)"
    )
    op.execute(
        "CREATE INDEX ix_job_posting_skills__requirement_type ON core.job_posting_skills (requirement_type)"
    )
    op.execute(
        "CREATE INDEX ix_job_posting_skills__extracted_record_id ON core.job_posting_skills (extracted_record_id)"
    )

    op.execute(
        """
        CREATE TABLE core.job_posting_occupations (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            job_posting_id UUID NOT NULL,
            occupation_id UUID NOT NULL,
            extracted_record_id BIGINT,
            is_primary BOOLEAN DEFAULT false NOT NULL,
            classification_method VARCHAR(100),
            classifier_version VARCHAR(100),
            confidence NUMERIC(5,4),
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_job_posting_occupations PRIMARY KEY (id),
            CONSTRAINT fk_job_posting_occupations__job_posting_id__job_postings
                FOREIGN KEY (job_posting_id) REFERENCES core.job_postings(id) ON DELETE CASCADE,
            CONSTRAINT fk_job_posting_occupations__occupation_id__occupations
                FOREIGN KEY (occupation_id) REFERENCES taxonomy.occupations(id) ON DELETE RESTRICT,
            CONSTRAINT fk_job_posting_occupations__extracted_record_id__extracted_records
                FOREIGN KEY (extracted_record_id) REFERENCES ingestion.extracted_records(id)
                ON DELETE SET NULL,
            CONSTRAINT uq_job_posting_occupations__job_occupation
                UNIQUE (job_posting_id, occupation_id),
            CONSTRAINT ck_job_posting_occupations__confidence CHECK
                (confidence IS NULL OR confidence BETWEEN 0 AND 1)
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_job_posting_occupations__one_primary ON core.job_posting_occupations (job_posting_id) WHERE is_primary"
    )
    op.execute(
        "CREATE INDEX ix_job_posting_occupations__occupation_id ON core.job_posting_occupations (occupation_id)"
    )
    op.execute(
        "CREATE INDEX ix_job_posting_occupations__job_posting_id ON core.job_posting_occupations (job_posting_id)"
    )
    op.execute(
        "CREATE INDEX ix_job_posting_occupations__extracted_record_id ON core.job_posting_occupations (extracted_record_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE core.job_posting_occupations")
    op.execute("DROP TABLE core.job_posting_skills")
    op.execute("DROP TABLE core.salary_offers")
    op.execute("DROP TABLE core.job_posting_locations")
    op.execute("DROP TABLE core.job_posting_descriptions")
    op.execute("DROP TABLE core.job_postings")
    op.execute("DROP TABLE core.company_domains")
    op.execute("DROP TABLE core.company_aliases")
    op.execute("DROP TABLE core.companies")
    op.execute("DROP TABLE core.locations")
    op.execute("DROP TABLE taxonomy.skill_aliases")
    op.execute("DROP TRIGGER trg_skills__taxonomy_type ON taxonomy.skills")
    op.execute("DROP TABLE taxonomy.skills")
    op.execute("DROP TABLE taxonomy.occupation_aliases")
    op.execute("DROP TRIGGER trg_occupations__taxonomy_type ON taxonomy.occupations")
    op.execute("DROP TABLE taxonomy.occupations")
    op.execute("DROP FUNCTION taxonomy.enforce_taxonomy_entity_type()")
    op.execute("DROP TABLE taxonomy.seniority_levels")
    op.execute("DROP TABLE taxonomy.employment_types")
    op.execute(
        "DROP TRIGGER trg_taxonomy_versions__immutable_type " "ON taxonomy.taxonomy_versions"
    )
    op.execute("DROP FUNCTION taxonomy.prevent_taxonomy_type_change()")
    op.execute("DROP TABLE taxonomy.taxonomy_versions")
    op.execute(
        "ALTER TABLE ingestion.extracted_records "
        "DROP CONSTRAINT uq_extracted_records__id_source_identity"
    )
    op.execute("DROP SCHEMA core")
    op.execute("DROP SCHEMA taxonomy")
