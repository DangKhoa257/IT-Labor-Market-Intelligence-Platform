"""Create private serving storage and the function-only API contract."""

from alembic import op

revision = "20260727_0006"
down_revision = "20260727_0005"
branch_labels = None
depends_on = None


CLIENT_ROLES = "anon, authenticated, service_role"


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS serving")
    op.execute("CREATE SCHEMA IF NOT EXISTS api")
    op.execute("REVOKE ALL ON SCHEMA serving FROM PUBLIC")
    op.execute("REVOKE ALL ON SCHEMA api FROM PUBLIC")

    op.execute(
        """
        CREATE TABLE serving.refresh_runs (
            id UUID DEFAULT gen_random_uuid() NOT NULL,
            run_type VARCHAR(30) NOT NULL,
            status VARCHAR(30) DEFAULT 'pending' NOT NULL,
            document_version VARCHAR(100) NOT NULL,
            source_id UUID,
            watermark_observed_at TIMESTAMPTZ,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            rows_upserted BIGINT DEFAULT 0 NOT NULL,
            rows_deleted BIGINT DEFAULT 0 NOT NULL,
            salary_rows_replaced BIGINT DEFAULT 0 NOT NULL,
            error_count INTEGER DEFAULT 0 NOT NULL,
            configuration_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            metrics_json JSONB DEFAULT '{}'::jsonb NOT NULL,
            error_message TEXT,
            created_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_serving_refresh_runs PRIMARY KEY (id),
            CONSTRAINT fk_serving_refresh_runs__source_id__sources
                FOREIGN KEY (source_id) REFERENCES ingestion.sources(id) ON DELETE SET NULL,
            CONSTRAINT ck_serving_refresh_runs__run_type CHECK
                (run_type IN ('incremental','backfill','rebuild','validation','test')),
            CONSTRAINT ck_serving_refresh_runs__status CHECK
                (status IN
                    ('pending','running','succeeded','partially_succeeded','failed','cancelled')),
            CONSTRAINT ck_serving_refresh_runs__document_version CHECK
                (length(trim(document_version)) > 0),
            CONSTRAINT ck_serving_refresh_runs__counters CHECK
                (rows_upserted >= 0 AND rows_deleted >= 0
                 AND salary_rows_replaced >= 0 AND error_count >= 0),
            CONSTRAINT ck_serving_refresh_runs__json_objects CHECK
                (jsonb_typeof(configuration_json) = 'object'
                 AND jsonb_typeof(metrics_json) = 'object'),
            CONSTRAINT ck_serving_refresh_runs__timestamps CHECK
                (finished_at IS NULL OR
                    (started_at IS NOT NULL AND finished_at >= started_at)),
            CONSTRAINT ck_serving_refresh_runs__lifecycle CHECK
                ((status = 'pending' AND started_at IS NULL AND finished_at IS NULL)
                 OR (status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL)
                 OR (status IN ('succeeded','partially_succeeded','failed','cancelled')
                     AND started_at IS NOT NULL AND finished_at IS NOT NULL))
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_serving_refresh_runs__status_created_at "
        "ON serving.refresh_runs (status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_serving_refresh_runs__source_created_at "
        "ON serving.refresh_runs (source_id, created_at DESC) WHERE source_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_serving_refresh_runs__version_created_at "
        "ON serving.refresh_runs (document_version, created_at DESC)"
    )

    op.execute(
        """
        CREATE TABLE serving.job_search_documents (
            job_posting_id UUID NOT NULL,
            observation_id BIGINT NOT NULL,
            source_id UUID NOT NULL,
            source_job_id VARCHAR(255) NOT NULL,
            company_id UUID,
            source_url TEXT NOT NULL,
            canonical_url TEXT,
            title TEXT NOT NULL,
            title_normalized TEXT,
            company_name TEXT,
            description_excerpt TEXT,
            employment_type_code VARCHAR(30),
            seniority_level_code VARCHAR(30),
            work_mode VARCHAR(30),
            status VARCHAR(20) NOT NULL,
            posted_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ,
            first_seen_at TIMESTAMPTZ NOT NULL,
            last_seen_at TIMESTAMPTZ NOT NULL,
            location_ids UUID[] DEFAULT '{}'::uuid[] NOT NULL,
            location_labels TEXT[] DEFAULT '{}'::text[] NOT NULL,
            locations_json JSONB DEFAULT '[]'::jsonb NOT NULL,
            occupation_ids UUID[] DEFAULT '{}'::uuid[] NOT NULL,
            occupation_names TEXT[] DEFAULT '{}'::text[] NOT NULL,
            occupations_json JSONB DEFAULT '[]'::jsonb NOT NULL,
            skill_ids UUID[] DEFAULT '{}'::uuid[] NOT NULL,
            skill_names TEXT[] DEFAULT '{}'::text[] NOT NULL,
            skills_json JSONB DEFAULT '[]'::jsonb NOT NULL,
            salary_disclosed BOOLEAN DEFAULT false NOT NULL,
            search_vector TSVECTOR NOT NULL,
            refresh_run_id UUID NOT NULL,
            document_version VARCHAR(100) NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_job_search_documents PRIMARY KEY (job_posting_id),
            CONSTRAINT uq_job_search_documents__observation_id UNIQUE (observation_id),
            CONSTRAINT fk_job_search_documents__job_posting_id__job_postings
                FOREIGN KEY (job_posting_id) REFERENCES core.job_postings(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_search_documents__observation_id__job_observations
                FOREIGN KEY (observation_id) REFERENCES history.job_observations(id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_job_search_documents__source_id__sources
                FOREIGN KEY (source_id) REFERENCES ingestion.sources(id) ON DELETE RESTRICT,
            CONSTRAINT fk_job_search_documents__company_id__companies
                FOREIGN KEY (company_id) REFERENCES core.companies(id) ON DELETE RESTRICT,
            CONSTRAINT fk_job_search_documents__refresh_run_id__refresh_runs
                FOREIGN KEY (refresh_run_id) REFERENCES serving.refresh_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_job_search_documents__required_text CHECK
                (length(trim(source_job_id)) > 0 AND length(trim(title)) > 0
                 AND length(trim(document_version)) > 0),
            CONSTRAINT ck_job_search_documents__source_url CHECK
                (source_url ~ '^https?://'),
            CONSTRAINT ck_job_search_documents__canonical_url CHECK
                (canonical_url IS NULL OR canonical_url ~ '^https?://'),
            CONSTRAINT ck_job_search_documents__excerpt CHECK
                (description_excerpt IS NULL OR length(description_excerpt) <= 1200),
            CONSTRAINT ck_job_search_documents__json_arrays CHECK
                (jsonb_typeof(locations_json) = 'array'
                 AND jsonb_typeof(occupations_json) = 'array'
                 AND jsonb_typeof(skills_json) = 'array'),
            CONSTRAINT ck_job_search_documents__array_cardinality CHECK
                (cardinality(location_ids) = cardinality(location_labels)
                 AND cardinality(occupation_ids) = cardinality(occupation_names)
                 AND cardinality(skill_ids) = cardinality(skill_names)),
            CONSTRAINT ck_job_search_documents__array_nulls CHECK
                (array_position(location_ids, NULL) IS NULL
                 AND array_position(location_labels, NULL) IS NULL
                 AND array_position(occupation_ids, NULL) IS NULL
                 AND array_position(occupation_names, NULL) IS NULL
                 AND array_position(skill_ids, NULL) IS NULL
                 AND array_position(skill_names, NULL) IS NULL),
            CONSTRAINT ck_job_search_documents__seen_dates CHECK
                (last_seen_at >= first_seen_at),
            CONSTRAINT ck_job_search_documents__posting_dates CHECK
                (expires_at IS NULL OR posted_at IS NULL OR expires_at >= posted_at)
        )
        """
    )
    op.execute(
        """
        CREATE FUNCTION serving.build_job_search_document()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, serving
        AS $$
        DECLARE
            posting core.job_postings%ROWTYPE;
            observation history.job_observations%ROWTYPE;
            run serving.refresh_runs%ROWTYPE;
            description_text TEXT;
        BEGIN
            IF TG_OP = 'UPDATE' AND NEW.job_posting_id IS DISTINCT FROM OLD.job_posting_id THEN
                RAISE EXCEPTION 'serving document job identity is immutable'
                    USING ERRCODE = '23514';
            END IF;

            SELECT * INTO posting FROM core.job_postings
            WHERE id = NEW.job_posting_id FOR UPDATE;
            IF NOT FOUND OR posting.current_observation_id IS DISTINCT FROM NEW.observation_id THEN
                RAISE EXCEPTION 'serving document requires the current observation'
                    USING ERRCODE = '23514';
            END IF;
            SELECT * INTO observation FROM history.job_observations
            WHERE id = NEW.observation_id FOR UPDATE;
            IF NOT FOUND OR observation.job_posting_id != NEW.job_posting_id
               OR observation.source_id != posting.source_id THEN
                RAISE EXCEPTION 'serving document observation lineage mismatch'
                    USING ERRCODE = '23514';
            END IF;
            SELECT * INTO run FROM serving.refresh_runs
            WHERE id = NEW.refresh_run_id FOR UPDATE;
            IF NOT FOUND OR (run.source_id IS NOT NULL
                             AND run.source_id != observation.source_id)
               OR NEW.document_version IS DISTINCT FROM run.document_version THEN
                RAISE EXCEPTION 'serving document refresh lineage mismatch'
                    USING ERRCODE = '23514';
            END IF;

            NEW.source_id := observation.source_id;
            NEW.source_job_id := observation.source_job_id;
            NEW.company_id := observation.company_id;
            NEW.source_url := observation.source_url;
            NEW.canonical_url := observation.canonical_url;
            NEW.title := observation.title_raw;
            NEW.title_normalized := observation.title_normalized;
            SELECT canonical_name INTO NEW.company_name FROM core.companies
            WHERE id = observation.company_id;
            NEW.company_name := COALESCE(NEW.company_name, observation.company_name_raw);
            SELECT left(description.description_text, 1200)
              INTO description_text
              FROM history.observation_descriptions AS description
             WHERE description.observation_id = observation.id
               AND description.description_text IS NOT NULL
               AND description.redaction_status NOT IN ('redacted','expired');
            NEW.description_excerpt := description_text;
            NEW.employment_type_code := observation.employment_type_code;
            NEW.seniority_level_code := observation.seniority_level_code;
            NEW.work_mode := observation.work_mode;
            NEW.status := observation.status;
            NEW.posted_at := observation.posted_at;
            NEW.expires_at := observation.expires_at;
            NEW.first_seen_at := posting.first_seen_at;
            NEW.last_seen_at := posting.last_seen_at;

            SELECT COALESCE(array_agg(location.id ORDER BY location.canonical_label, location.id),
                            '{}'::uuid[]),
                   COALESCE(array_agg(location.canonical_label
                                      ORDER BY location.canonical_label, location.id),
                            '{}'::text[]),
                   COALESCE(jsonb_agg(jsonb_build_object(
                       'id', location.id, 'label', location.canonical_label,
                       'relationship_type', child.relationship_type,
                       'is_primary', child.is_primary, 'is_remote', child.is_remote,
                       'remote_scope', child.remote_scope)
                       ORDER BY location.canonical_label, location.id), '[]'::jsonb)
              INTO NEW.location_ids, NEW.location_labels, NEW.locations_json
              FROM history.observation_locations AS child
              JOIN core.locations AS location ON location.id = child.location_id
             WHERE child.observation_id = observation.id;
            SELECT COALESCE(array_agg(occupation.id
                                      ORDER BY child.is_primary DESC,
                                               occupation.canonical_name, occupation.id),
                            '{}'::uuid[]),
                   COALESCE(array_agg(occupation.canonical_name
                                      ORDER BY child.is_primary DESC,
                                               occupation.canonical_name, occupation.id),
                            '{}'::text[]),
                   COALESCE(jsonb_agg(jsonb_build_object(
                       'id', occupation.id, 'code', occupation.canonical_code,
                       'name', occupation.canonical_name, 'is_primary', child.is_primary)
                       ORDER BY child.is_primary DESC,
                                occupation.canonical_name, occupation.id), '[]'::jsonb)
              INTO NEW.occupation_ids, NEW.occupation_names, NEW.occupations_json
              FROM history.observation_occupations AS child
              JOIN taxonomy.occupations AS occupation ON occupation.id = child.occupation_id
             WHERE child.observation_id = observation.id;
            SELECT COALESCE(array_agg(skill.id
                                      ORDER BY skill.canonical_name, child.requirement_type,
                                               skill.id), '{}'::uuid[]),
                   COALESCE(array_agg(skill.canonical_name
                                      ORDER BY skill.canonical_name, child.requirement_type,
                                               skill.id), '{}'::text[]),
                   COALESCE(jsonb_agg(jsonb_build_object(
                       'id', skill.id, 'name', skill.canonical_name,
                       'requirement_type', child.requirement_type)
                       ORDER BY skill.canonical_name, child.requirement_type, skill.id),
                            '[]'::jsonb)
              INTO NEW.skill_ids, NEW.skill_names, NEW.skills_json
              FROM history.observation_skills AS child
              JOIN taxonomy.skills AS skill ON skill.id = child.skill_id
             WHERE child.observation_id = observation.id;
            NEW.salary_disclosed := EXISTS (
                SELECT 1 FROM history.observation_salaries
                WHERE observation_id = observation.id AND is_disclosed
            );
            NEW.search_vector :=
                setweight(to_tsvector('simple', COALESCE(NEW.title, '') || ' ' ||
                    COALESCE(NEW.title_normalized, '')), 'A') ||
                setweight(to_tsvector('simple', COALESCE(NEW.company_name, '') || ' ' ||
                    array_to_string(NEW.occupation_names, ' ') || ' ' ||
                    array_to_string(NEW.skill_names, ' ')), 'B') ||
                setweight(to_tsvector('simple',
                    array_to_string(NEW.location_labels, ' ')), 'C') ||
                setweight(to_tsvector('simple', COALESCE(NEW.description_excerpt, '')), 'D');
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """CREATE TRIGGER trg_job_search_documents__build
        BEFORE INSERT OR UPDATE ON serving.job_search_documents
        FOR EACH ROW EXECUTE FUNCTION serving.build_job_search_document()"""
    )
    for statement in (
        "CREATE INDEX ix_job_search_documents__search_vector ON serving.job_search_documents USING GIN (search_vector)",
        "CREATE INDEX ix_job_search_documents__skill_ids ON serving.job_search_documents USING GIN (skill_ids)",
        "CREATE INDEX ix_job_search_documents__occupation_ids ON serving.job_search_documents USING GIN (occupation_ids)",
        "CREATE INDEX ix_job_search_documents__location_ids ON serving.job_search_documents USING GIN (location_ids)",
        "CREATE INDEX ix_job_search_documents__status_posted ON serving.job_search_documents (status, posted_at DESC, job_posting_id)",
        "CREATE INDEX ix_job_search_documents__source_posted ON serving.job_search_documents (source_id, posted_at DESC)",
        "CREATE INDEX ix_job_search_documents__company_posted ON serving.job_search_documents (company_id, posted_at DESC) WHERE company_id IS NOT NULL",
        "CREATE INDEX ix_job_search_documents__employment_posted ON serving.job_search_documents (employment_type_code, posted_at DESC)",
        "CREATE INDEX ix_job_search_documents__seniority_posted ON serving.job_search_documents (seniority_level_code, posted_at DESC)",
        "CREATE INDEX ix_job_search_documents__work_mode_posted ON serving.job_search_documents (work_mode, posted_at DESC)",
        "CREATE INDEX ix_job_search_documents__refresh_run_id ON serving.job_search_documents (refresh_run_id)",
    ):
        op.execute(statement)

    op.execute(
        """
        CREATE TABLE serving.job_search_salary_offers (
            id BIGINT GENERATED ALWAYS AS IDENTITY,
            job_posting_id UUID NOT NULL,
            observation_salary_id BIGINT NOT NULL,
            currency CHAR(3), period VARCHAR(20), tax_basis VARCHAR(20) NOT NULL,
            compensation_type VARCHAR(30) NOT NULL,
            is_disclosed BOOLEAN NOT NULL, is_negotiable BOOLEAN NOT NULL,
            is_estimated BOOLEAN NOT NULL,
            amount_min NUMERIC(20,2), amount_max NUMERIC(20,2), amount_exact NUMERIC(20,2),
            normalized_monthly_min NUMERIC(20,2), normalized_monthly_max NUMERIC(20,2),
            normalized_annual_min NUMERIC(20,2), normalized_annual_max NUMERIC(20,2),
            refresh_run_id UUID NOT NULL,
            updated_at TIMESTAMPTZ DEFAULT now() NOT NULL,
            CONSTRAINT pk_job_search_salary_offers PRIMARY KEY (id),
            CONSTRAINT uq_job_search_salary_offers__observation_salary_id
                UNIQUE (observation_salary_id),
            CONSTRAINT fk_job_search_salary_offers__job_document
                FOREIGN KEY (job_posting_id)
                REFERENCES serving.job_search_documents(job_posting_id) ON DELETE CASCADE,
            CONSTRAINT fk_job_search_salary_offers__history_salary
                FOREIGN KEY (observation_salary_id)
                REFERENCES history.observation_salaries(id) ON DELETE RESTRICT,
            CONSTRAINT fk_job_search_salary_offers__refresh_run
                FOREIGN KEY (refresh_run_id) REFERENCES serving.refresh_runs(id)
                ON DELETE RESTRICT,
            CONSTRAINT ck_job_search_salary_offers__currency CHECK
                (currency IS NULL OR currency ~ '^[A-Z]{3}$'),
            CONSTRAINT ck_job_search_salary_offers__period CHECK
                (period IS NULL OR period IN ('hour','day','week','month','year','project','unknown')),
            CONSTRAINT ck_job_search_salary_offers__tax_basis CHECK
                (tax_basis IN ('gross','net','unknown')),
            CONSTRAINT ck_job_search_salary_offers__compensation CHECK
                (compensation_type IN ('base_salary','total_compensation','bonus','commission',
                    'equity','allowance','other')),
            CONSTRAINT ck_job_search_salary_offers__nonnegative CHECK
                ((amount_min IS NULL OR amount_min >= 0) AND (amount_max IS NULL OR amount_max >= 0)
                 AND (amount_exact IS NULL OR amount_exact >= 0)
                 AND (normalized_monthly_min IS NULL OR normalized_monthly_min >= 0)
                 AND (normalized_monthly_max IS NULL OR normalized_monthly_max >= 0)
                 AND (normalized_annual_min IS NULL OR normalized_annual_min >= 0)
                 AND (normalized_annual_max IS NULL OR normalized_annual_max >= 0)),
            CONSTRAINT ck_job_search_salary_offers__ranges CHECK
                ((amount_min IS NULL OR amount_max IS NULL OR amount_min <= amount_max)
                 AND (normalized_monthly_min IS NULL OR normalized_monthly_max IS NULL
                      OR normalized_monthly_min <= normalized_monthly_max)
                 AND (normalized_annual_min IS NULL OR normalized_annual_max IS NULL
                      OR normalized_annual_min <= normalized_annual_max)),
            CONSTRAINT ck_job_search_salary_offers__disclosure CHECK
                ((NOT is_disclosed OR amount_min IS NOT NULL OR amount_max IS NOT NULL
                  OR amount_exact IS NOT NULL)
                 AND (is_disclosed OR is_estimated
                      OR (amount_min IS NULL AND amount_max IS NULL AND amount_exact IS NULL)))
        )
        """
    )
    op.execute(
        """
        CREATE FUNCTION serving.validate_search_salary_offer()
        RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, serving
        AS $$
        BEGIN
            PERFORM 1 FROM serving.job_search_documents
            WHERE job_posting_id = NEW.job_posting_id FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'serving salary requires parent document'
                    USING ERRCODE = '23514';
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM history.observation_salaries AS salary
                JOIN serving.job_search_documents AS document
                  ON document.job_posting_id = NEW.job_posting_id
                 AND document.observation_id = salary.observation_id
                WHERE salary.id = NEW.observation_salary_id
                  AND document.refresh_run_id = NEW.refresh_run_id
                  AND NEW.currency IS NOT DISTINCT FROM salary.currency
                  AND NEW.period IS NOT DISTINCT FROM salary.period
                  AND NEW.tax_basis = salary.tax_basis
                  AND NEW.compensation_type = salary.compensation_type
                  AND NEW.is_disclosed = salary.is_disclosed
                  AND NEW.is_negotiable = salary.is_negotiable
                  AND NEW.is_estimated = salary.is_estimated
                  AND NEW.amount_min IS NOT DISTINCT FROM salary.amount_min
                  AND NEW.amount_max IS NOT DISTINCT FROM salary.amount_max
                  AND NEW.amount_exact IS NOT DISTINCT FROM salary.amount_exact
                  AND NEW.normalized_monthly_min IS NOT DISTINCT FROM salary.normalized_monthly_min
                  AND NEW.normalized_monthly_max IS NOT DISTINCT FROM salary.normalized_monthly_max
                  AND NEW.normalized_annual_min IS NOT DISTINCT FROM salary.normalized_annual_min
                  AND NEW.normalized_annual_max IS NOT DISTINCT FROM salary.normalized_annual_max
            ) THEN
                RAISE EXCEPTION 'serving salary lineage mismatch' USING ERRCODE = '23514';
            END IF;
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """CREATE TRIGGER trg_job_search_salary_offers__validate
        BEFORE INSERT OR UPDATE ON serving.job_search_salary_offers
        FOR EACH ROW EXECUTE FUNCTION serving.validate_search_salary_offer()"""
    )
    op.execute(
        """
        CREATE FUNCTION serving.rebuild_job_search_salary_offers()
        RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, serving
        AS $$
        BEGIN
            PERFORM 1 FROM serving.job_search_documents
            WHERE job_posting_id = NEW.job_posting_id FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'serving salary projection requires parent document'
                    USING ERRCODE = '23514';
            END IF;

            DELETE FROM serving.job_search_salary_offers
            WHERE job_posting_id = NEW.job_posting_id;
            INSERT INTO serving.job_search_salary_offers (
                job_posting_id, observation_salary_id, currency, period, tax_basis,
                compensation_type, is_disclosed, is_negotiable, is_estimated,
                amount_min, amount_max, amount_exact, normalized_monthly_min,
                normalized_monthly_max, normalized_annual_min, normalized_annual_max,
                refresh_run_id
            )
            SELECT NEW.job_posting_id, salary.id, salary.currency, salary.period,
                   salary.tax_basis, salary.compensation_type, salary.is_disclosed,
                   salary.is_negotiable, salary.is_estimated, salary.amount_min,
                   salary.amount_max, salary.amount_exact, salary.normalized_monthly_min,
                   salary.normalized_monthly_max, salary.normalized_annual_min,
                   salary.normalized_annual_max, NEW.refresh_run_id
            FROM history.observation_salaries AS salary
            WHERE salary.observation_id = NEW.observation_id
            ORDER BY salary.id;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """CREATE TRIGGER trg_job_search_documents__rebuild_salaries
        AFTER INSERT OR UPDATE ON serving.job_search_documents
        FOR EACH ROW EXECUTE FUNCTION serving.rebuild_job_search_salary_offers()"""
    )
    for statement in (
        "CREATE INDEX ix_search_salary_offers__job_id ON serving.job_search_salary_offers (job_posting_id)",
        "CREATE INDEX ix_search_salary_offers__category ON serving.job_search_salary_offers (currency, period, tax_basis)",
        "CREATE INDEX ix_search_salary_offers__range ON serving.job_search_salary_offers (currency, period, tax_basis, amount_min, amount_max) WHERE is_disclosed",
        "CREATE INDEX ix_search_salary_offers__monthly ON serving.job_search_salary_offers (currency, normalized_monthly_min, normalized_monthly_max)",
        "CREATE INDEX ix_search_salary_offers__refresh_run_id ON serving.job_search_salary_offers (refresh_run_id)",
    ):
        op.execute(statement)

    op.execute(
        """
        CREATE FUNCTION serving.prevent_refresh_lineage_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF (NEW.source_id IS DISTINCT FROM OLD.source_id
                OR NEW.document_version IS DISTINCT FROM OLD.document_version)
               AND (EXISTS (SELECT 1 FROM serving.job_search_documents
                            WHERE refresh_run_id = OLD.id)
                    OR EXISTS (SELECT 1 FROM serving.job_search_salary_offers
                               WHERE refresh_run_id = OLD.id)) THEN
                RAISE EXCEPTION 'referenced serving refresh lineage is immutable'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """CREATE TRIGGER trg_serving_refresh_runs__lineage_immutable
        BEFORE UPDATE ON serving.refresh_runs
        FOR EACH ROW EXECUTE FUNCTION serving.prevent_refresh_lineage_mutation()"""
    )

    op.execute(
        """
        CREATE FUNCTION serving.prevent_served_observation_child_insert()
        RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, serving
        AS $$
        BEGIN
            PERFORM 1 FROM history.job_observations
            WHERE id = NEW.observation_id FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'historical child observation does not exist'
                    USING ERRCODE = '23514';
            END IF;
            IF EXISTS (
                SELECT 1 FROM serving.job_search_documents
                WHERE observation_id = NEW.observation_id
            ) THEN
                RAISE EXCEPTION 'served observation snapshot is finalized'
                    USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    for table_name in (
        "observation_descriptions",
        "observation_locations",
        "observation_salaries",
        "observation_skills",
        "observation_occupations",
    ):
        op.execute(
            f"""CREATE TRIGGER trg_{table_name}__serving_finalized
            BEFORE INSERT ON history.{table_name}
            FOR EACH ROW
            EXECUTE FUNCTION serving.prevent_served_observation_child_insert()"""
        )

    op.execute(
        """
        CREATE FUNCTION serving.invalidate_redacted_description_document()
        RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
        SET search_path = pg_catalog, serving
        AS $$
        BEGIN
            IF OLD.description_text IS NOT NULL
               AND NEW.description_text IS NULL
               AND NEW.redaction_status IN ('redacted', 'expired')
               AND OLD.redaction_status NOT IN ('redacted', 'expired') THEN
                PERFORM 1 FROM serving.job_search_documents
                WHERE observation_id = NEW.observation_id FOR UPDATE;

                PERFORM 1 FROM history.job_observations
                WHERE id = NEW.observation_id FOR UPDATE;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'description observation does not exist'
                        USING ERRCODE = '23514';
                END IF;

                DELETE FROM serving.job_search_documents
                WHERE observation_id = NEW.observation_id;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """CREATE TRIGGER trg_observation_descriptions__serving_redaction
        BEFORE UPDATE OF description_text, redaction_status
        ON history.observation_descriptions
        FOR EACH ROW
        EXECUTE FUNCTION serving.invalidate_redacted_description_document()"""
    )

    op.execute("ALTER TABLE serving.refresh_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE serving.job_search_documents ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE serving.job_search_salary_offers ENABLE ROW LEVEL SECURITY")

    _create_views()
    _create_api_functions()
    _apply_grants()


def _create_views() -> None:
    op.execute(
        """
        CREATE VIEW serving.v_current_job_cards AS
        SELECT document.job_posting_id, document.observation_id, document.source_id,
               source.slug AS source_slug, source.display_name AS source_display_name,
               document.source_job_id, document.company_id, document.source_url,
               document.canonical_url, document.title, document.title_normalized,
               document.company_name, document.description_excerpt,
               document.employment_type_code, document.seniority_level_code,
               document.work_mode, document.status, document.posted_at, document.expires_at,
               document.first_seen_at, document.last_seen_at, document.location_ids,
               document.location_labels, document.locations_json, document.occupation_ids,
               document.occupation_names, document.occupations_json, document.skill_ids,
               document.skill_names, document.skills_json, document.salary_disclosed,
               document.search_vector, document.document_version, document.updated_at
        FROM serving.job_search_documents AS document
        JOIN core.job_postings AS posting ON posting.id = document.job_posting_id
        JOIN ingestion.sources AS source ON source.id = document.source_id
        WHERE document.observation_id = posting.current_observation_id
        """
    )
    op.execute(
        """
        CREATE VIEW serving.v_market_overview_daily AS
        SELECT metric.metric_date, source.source_id, source.slug::text AS source_slug,
               metric.employment_type_code, metric.seniority_level_code, metric.work_mode,
               metric.active_posting_count, metric.new_posting_count,
               metric.closed_posting_count, metric.expired_posting_count,
               metric.removed_posting_count, metric.reactivated_posting_count,
               metric.content_changed_count, metric.salary_disclosed_count,
               metric.remote_posting_count, metric.calculation_version, metric.calculated_at
        FROM analytics.daily_market_metrics AS metric
        JOIN analytics.dim_sources AS source ON source.source_key = metric.source_key
        """
    )
    op.execute(
        """
        CREATE VIEW serving.v_company_hiring_daily AS
        SELECT metric.metric_date, source.source_id, source.slug::text AS source_slug,
               source.display_name::text AS source_display_name,
               company.company_id, company.canonical_name::text AS company_name,
               company.company_type::text AS company_type,
               metric.active_posting_count, metric.new_posting_count,
               metric.closed_posting_count, metric.unique_occupation_count,
               metric.unique_skill_count, metric.salary_disclosed_count,
               metric.remote_posting_count, metric.calculation_version, metric.calculated_at
        FROM analytics.daily_company_hiring AS metric
        JOIN analytics.dim_sources AS source ON source.source_key = metric.source_key
        JOIN analytics.dim_companies AS company ON company.company_key = metric.company_key
        """
    )
    op.execute(
        """
        CREATE VIEW serving.v_location_demand_daily AS
        SELECT metric.metric_date, source.source_id, source.slug::text AS source_slug,
               location.location_id, location.canonical_label::text AS location_label,
               location.country_code::text AS country_code,
               location.admin_level_1::text AS admin_level_1,
               location.admin_level_2::text AS admin_level_2,
               location.locality::text AS locality, metric.work_mode::text AS work_mode,
               metric.active_posting_count, metric.new_posting_count,
               metric.closed_posting_count, metric.salary_disclosed_count,
               metric.calculation_version, metric.calculated_at
        FROM analytics.daily_location_demand AS metric
        JOIN analytics.dim_sources AS source ON source.source_key = metric.source_key
        JOIN analytics.dim_locations AS location ON location.location_key = metric.location_key
        """
    )
    op.execute(
        """
        CREATE VIEW serving.v_occupation_demand_daily AS
        SELECT metric.metric_date, source.source_id, source.slug::text AS source_slug,
               occupation.occupation_id, occupation.canonical_name::text AS occupation_name,
               occupation.canonical_code::text AS occupation_code,
               occupation.taxonomy_version::text AS taxonomy_version,
               metric.active_posting_count, metric.new_posting_count,
               metric.closed_posting_count, metric.salary_disclosed_count,
               metric.remote_posting_count, metric.calculation_version, metric.calculated_at
        FROM analytics.daily_occupation_demand AS metric
        JOIN analytics.dim_sources AS source ON source.source_key = metric.source_key
        JOIN analytics.dim_occupations AS occupation
          ON occupation.occupation_key = metric.occupation_key
        """
    )
    op.execute(
        """
        CREATE VIEW serving.v_skill_demand_daily AS
        SELECT metric.metric_date, source.source_id, source.slug::text AS source_slug,
               skill.skill_id, skill.canonical_name::text AS skill_name,
               skill.canonical_code::text AS skill_code,
               skill.skill_type::text AS skill_type,
               skill.taxonomy_version::text AS taxonomy_version,
               metric.requirement_type::text AS requirement_type,
               metric.active_posting_count, metric.new_posting_count,
               metric.closed_posting_count, metric.company_count, metric.occupation_count,
               metric.calculation_version, metric.calculated_at
        FROM analytics.daily_skill_demand AS metric
        JOIN analytics.dim_sources AS source ON source.source_key = metric.source_key
        JOIN analytics.dim_skills AS skill ON skill.skill_key = metric.skill_key
        """
    )
    op.execute(
        """
        CREATE VIEW serving.v_salary_metrics_daily AS
        SELECT metric.metric_date, source.source_id, source.slug::text AS source_slug,
               occupation.occupation_id, occupation.canonical_name::text AS occupation_name,
               location.location_id, location.canonical_label::text AS location_label,
               metric.currency::text AS currency, metric.period::text AS period,
               metric.tax_basis::text AS tax_basis,
               metric.disclosed_salary_count, metric.estimated_salary_count,
               metric.negotiable_salary_count, metric.amount_min_average,
               metric.amount_max_average, metric.amount_exact_average,
               metric.normalized_monthly_min_average, metric.normalized_monthly_max_average,
               metric.normalized_annual_min_average, metric.normalized_annual_max_average,
               metric.normalized_monthly_min_median, metric.normalized_monthly_max_median,
               metric.normalized_annual_min_median, metric.normalized_annual_max_median,
               metric.calculation_version, metric.calculated_at
        FROM analytics.daily_salary_metrics AS metric
        JOIN analytics.dim_sources AS source ON source.source_key = metric.source_key
        JOIN analytics.dim_occupations AS occupation
          ON occupation.occupation_key = metric.occupation_key
        JOIN analytics.dim_locations AS location ON location.location_key = metric.location_key
        """
    )


def _create_api_functions() -> None:
    _create_search_function()
    _create_get_job_function()
    _create_dashboard_functions()


def _validate_dashboard_sql() -> str:
    return """
        IF p_start_date IS NULL OR p_end_date IS NULL OR p_end_date < p_start_date
           OR p_end_date - p_start_date > 366 THEN
            RAISE EXCEPTION 'invalid date window' USING ERRCODE = '22023';
        END IF;
    """


def _create_search_function() -> None:
    op.execute(
        """
        CREATE FUNCTION api.search_jobs_v1(
          p_query TEXT DEFAULT NULL, p_source_ids UUID[] DEFAULT NULL,
          p_company_ids UUID[] DEFAULT NULL, p_location_ids UUID[] DEFAULT NULL,
          p_occupation_ids UUID[] DEFAULT NULL, p_skill_ids UUID[] DEFAULT NULL,
          p_employment_types TEXT[] DEFAULT NULL, p_seniority_levels TEXT[] DEFAULT NULL,
          p_work_modes TEXT[] DEFAULT NULL,
          p_statuses TEXT[] DEFAULT ARRAY['active']::text[],
          p_posted_after TIMESTAMPTZ DEFAULT NULL, p_salary_currency TEXT DEFAULT NULL,
          p_salary_period TEXT DEFAULT NULL, p_salary_tax_basis TEXT DEFAULT NULL,
          p_salary_min NUMERIC DEFAULT NULL, p_salary_max NUMERIC DEFAULT NULL,
          p_sort TEXT DEFAULT 'relevance', p_limit INTEGER DEFAULT 20, p_offset INTEGER DEFAULT 0
        ) RETURNS TABLE (
          job_posting_id UUID, observation_id BIGINT, title TEXT, company_id UUID,
          company_name TEXT, source_id UUID, source_slug TEXT, source_display_name TEXT,
          source_url TEXT, canonical_url TEXT, status TEXT, posted_at TIMESTAMPTZ,
          expires_at TIMESTAMPTZ, first_seen_at TIMESTAMPTZ, last_seen_at TIMESTAMPTZ,
          employment_type_code TEXT, seniority_level_code TEXT, work_mode TEXT,
          location_labels TEXT[], occupation_names TEXT[], skill_names TEXT[],
          salary_disclosed BOOLEAN, salary_offers_json JSONB, rank_score REAL,
          total_count BIGINT
        ) LANGUAGE plpgsql SECURITY DEFINER STABLE
        SET search_path = pg_catalog, api, serving AS $$
        BEGIN
          IF p_limit IS NULL OR p_offset IS NULL OR p_sort IS NULL
             OR p_limit NOT BETWEEN 1 AND 50 OR p_offset NOT BETWEEN 0 AND 1000
             OR p_sort NOT IN ('relevance','newest','oldest')
             OR (p_query IS NOT NULL AND char_length(p_query) > 500)
             OR cardinality(p_source_ids) > 100 OR array_position(p_source_ids, NULL) IS NOT NULL
             OR cardinality(p_company_ids) > 100 OR array_position(p_company_ids, NULL) IS NOT NULL
             OR cardinality(p_location_ids) > 100 OR array_position(p_location_ids, NULL) IS NOT NULL
             OR cardinality(p_occupation_ids) > 100 OR array_position(p_occupation_ids, NULL) IS NOT NULL
             OR cardinality(p_skill_ids) > 100 OR array_position(p_skill_ids, NULL) IS NOT NULL
             OR cardinality(p_employment_types) > 100 OR array_position(p_employment_types, NULL) IS NOT NULL
             OR cardinality(p_seniority_levels) > 100 OR array_position(p_seniority_levels, NULL) IS NOT NULL
             OR cardinality(p_work_modes) > 100 OR array_position(p_work_modes, NULL) IS NOT NULL
             OR cardinality(p_statuses) > 100 OR array_position(p_statuses, NULL) IS NOT NULL
             OR p_salary_min < 0 OR p_salary_max < 0
             OR (p_salary_min IS NOT NULL AND p_salary_max IS NOT NULL
                 AND p_salary_min > p_salary_max)
             OR ((p_salary_min IS NOT NULL OR p_salary_max IS NOT NULL)
                 AND (p_salary_currency IS NULL OR p_salary_period IS NULL)) THEN
            RAISE EXCEPTION 'invalid search parameters' USING ERRCODE = '22023';
          END IF;
          RETURN QUERY
          WITH matched AS (
            SELECT card.*,
                   CASE WHEN p_query IS NULL OR btrim(p_query) = '' THEN 0::real
                        ELSE ts_rank_cd(card.search_vector,
                             websearch_to_tsquery('simple', p_query)) END AS score,
                   COALESCE((SELECT jsonb_agg(jsonb_build_object(
                       'currency', salary.currency, 'period', salary.period,
                       'tax_basis', salary.tax_basis, 'compensation_type', salary.compensation_type,
                       'amount_min', salary.amount_min, 'amount_max', salary.amount_max,
                       'amount_exact', salary.amount_exact, 'is_disclosed', salary.is_disclosed)
                       ORDER BY salary.currency, salary.period, salary.tax_basis,
                                salary.compensation_type, salary.id)
                     FROM serving.job_search_salary_offers AS salary
                     WHERE salary.job_posting_id = card.job_posting_id), '[]'::jsonb) AS salaries
            FROM serving.v_current_job_cards AS card
            WHERE (p_query IS NULL OR btrim(p_query) = '' OR
                   card.search_vector @@ websearch_to_tsquery('simple', p_query))
              AND (p_source_ids IS NULL OR card.source_id = ANY(p_source_ids))
              AND (p_company_ids IS NULL OR card.company_id = ANY(p_company_ids))
              AND (p_location_ids IS NULL OR card.location_ids && p_location_ids)
              AND (p_occupation_ids IS NULL OR card.occupation_ids && p_occupation_ids)
              AND (p_skill_ids IS NULL OR card.skill_ids && p_skill_ids)
              AND (p_employment_types IS NULL OR card.employment_type_code = ANY(p_employment_types))
              AND (p_seniority_levels IS NULL OR card.seniority_level_code = ANY(p_seniority_levels))
              AND (p_work_modes IS NULL OR card.work_mode = ANY(p_work_modes))
              AND (p_statuses IS NULL OR card.status = ANY(p_statuses))
              AND (p_posted_after IS NULL OR card.posted_at >= p_posted_after)
              AND ((p_salary_currency IS NULL AND p_salary_period IS NULL
                    AND p_salary_tax_basis IS NULL AND p_salary_min IS NULL
                    AND p_salary_max IS NULL) OR EXISTS (
                  SELECT 1 FROM serving.job_search_salary_offers AS salary
                  WHERE salary.job_posting_id = card.job_posting_id AND salary.is_disclosed
                    AND (p_salary_currency IS NULL OR salary.currency = p_salary_currency)
                    AND (p_salary_period IS NULL OR salary.period = p_salary_period)
                    AND (p_salary_tax_basis IS NULL OR salary.tax_basis = p_salary_tax_basis)
                    AND (p_salary_min IS NULL OR
                         COALESCE(salary.amount_max, salary.amount_exact, salary.amount_min)
                         >= p_salary_min)
                    AND (p_salary_max IS NULL OR
                         COALESCE(salary.amount_min, salary.amount_exact, salary.amount_max)
                         <= p_salary_max)))
          ), counted AS (SELECT matched.*, count(*) OVER () AS matched_count FROM matched)
          SELECT counted.job_posting_id, counted.observation_id, counted.title,
                 counted.company_id, counted.company_name::text, counted.source_id,
                 counted.source_slug::text, counted.source_display_name::text, counted.source_url,
                 counted.canonical_url, counted.status::text, counted.posted_at, counted.expires_at,
                 counted.first_seen_at, counted.last_seen_at, counted.employment_type_code::text,
                 counted.seniority_level_code::text, counted.work_mode::text, counted.location_labels,
                 counted.occupation_names, counted.skill_names, counted.salary_disclosed,
                 counted.salaries, counted.score, counted.matched_count
          FROM counted
          ORDER BY CASE WHEN p_sort='relevance' AND btrim(COALESCE(p_query, '')) != ''
                        THEN counted.score END DESC,
                   CASE WHEN p_sort IN ('relevance','newest')
                        THEN counted.posted_at END DESC NULLS LAST,
                   CASE WHEN p_sort='oldest' THEN counted.posted_at END ASC NULLS LAST,
                   counted.job_posting_id
          LIMIT p_limit OFFSET p_offset;
        END; $$
        """
    )


def _create_get_job_function() -> None:
    op.execute(
        """
        CREATE FUNCTION api.get_job_v1(p_job_posting_id UUID)
        RETURNS TABLE (
          job_posting_id UUID, observation_id BIGINT, source_id UUID, source_slug TEXT,
          source_display_name TEXT, source_job_id TEXT, company_id UUID, source_url TEXT,
          canonical_url TEXT, title TEXT, title_normalized TEXT, company_name TEXT,
          description_excerpt TEXT, employment_type_code TEXT, seniority_level_code TEXT,
          work_mode TEXT, status TEXT, posted_at TIMESTAMPTZ, expires_at TIMESTAMPTZ,
          first_seen_at TIMESTAMPTZ, last_seen_at TIMESTAMPTZ, locations_json JSONB,
          occupations_json JSONB, skills_json JSONB, salary_disclosed BOOLEAN,
          salary_offers_json JSONB,
          document_version TEXT, updated_at TIMESTAMPTZ
        ) LANGUAGE sql SECURITY DEFINER STABLE
        SET search_path = pg_catalog, api, serving AS $$
          SELECT card.job_posting_id, card.observation_id, card.source_id, card.source_slug::text,
                 card.source_display_name::text, card.source_job_id::text, card.company_id, card.source_url,
                 card.canonical_url, card.title, card.title_normalized, card.company_name,
                 card.description_excerpt, card.employment_type_code::text,
                 card.seniority_level_code::text, card.work_mode::text, card.status::text, card.posted_at,
                 card.expires_at, card.first_seen_at, card.last_seen_at, card.locations_json,
                 card.occupations_json, card.skills_json, card.salary_disclosed,
                 COALESCE((SELECT jsonb_agg(jsonb_build_object(
                    'currency', salary.currency, 'period', salary.period,
                    'tax_basis', salary.tax_basis, 'compensation_type', salary.compensation_type,
                    'amount_min', salary.amount_min, 'amount_max', salary.amount_max,
                    'amount_exact', salary.amount_exact, 'is_disclosed', salary.is_disclosed)
                    ORDER BY salary.currency, salary.period, salary.tax_basis,
                             salary.compensation_type, salary.id)
                    FROM serving.job_search_salary_offers AS salary
                    WHERE salary.job_posting_id=card.job_posting_id), '[]'::jsonb),
                 card.document_version::text, card.updated_at
          FROM serving.v_current_job_cards AS card
          WHERE card.job_posting_id = p_job_posting_id
        $$
        """
    )


def _create_dashboard_functions() -> None:
    common = _validate_dashboard_sql()
    op.execute(
        f"""
        CREATE FUNCTION api.market_overview_v1(
          p_start_date DATE DEFAULT current_date - 30, p_end_date DATE DEFAULT current_date,
          p_source_ids UUID[] DEFAULT NULL, p_employment_types TEXT[] DEFAULT NULL,
          p_seniority_levels TEXT[] DEFAULT NULL, p_work_modes TEXT[] DEFAULT NULL)
        RETURNS TABLE (metric_date DATE, active_posting_count BIGINT,
          new_posting_count BIGINT, closed_posting_count BIGINT,
          expired_posting_count BIGINT, removed_posting_count BIGINT,
          reactivated_posting_count BIGINT, content_changed_count BIGINT,
          salary_disclosed_count BIGINT, remote_posting_count BIGINT)
        LANGUAGE plpgsql SECURITY DEFINER STABLE
        SET search_path = pg_catalog, api, serving AS $$ BEGIN {common}
          RETURN QUERY SELECT view.metric_date, sum(view.active_posting_count)::bigint,
            sum(view.new_posting_count)::bigint, sum(view.closed_posting_count)::bigint,
            sum(view.expired_posting_count)::bigint, sum(view.removed_posting_count)::bigint,
            sum(view.reactivated_posting_count)::bigint, sum(view.content_changed_count)::bigint,
            sum(view.salary_disclosed_count)::bigint, sum(view.remote_posting_count)::bigint
          FROM serving.v_market_overview_daily AS view
          WHERE view.metric_date BETWEEN p_start_date AND p_end_date
            AND (p_source_ids IS NULL OR view.source_id=ANY(p_source_ids))
            AND (p_employment_types IS NULL OR view.employment_type_code=ANY(p_employment_types))
            AND (p_seniority_levels IS NULL OR view.seniority_level_code=ANY(p_seniority_levels))
            AND (p_work_modes IS NULL OR view.work_mode=ANY(p_work_modes))
          GROUP BY view.metric_date ORDER BY view.metric_date; END; $$
        """
    )
    _create_dimension_dashboard_functions(common)


def _create_dimension_dashboard_functions(common: str) -> None:
    definitions = (
        (
            "company_hiring_v1",
            "company",
            "company_ids",
            "source_display_name TEXT, company_id UUID, company_name TEXT, company_type TEXT",
            "source_display_name, company_id, company_name, company_type",
            "",
            "active_posting_count, new_posting_count, closed_posting_count, unique_occupation_count, unique_skill_count, salary_disclosed_count, remote_posting_count",
        ),
        (
            "location_demand_v1",
            "location",
            "location_ids",
            "location_id UUID, location_label TEXT, country_code TEXT, admin_level_1 TEXT, admin_level_2 TEXT, locality TEXT, work_mode TEXT",
            "location_id, location_label, country_code, admin_level_1, admin_level_2, locality, work_mode",
            "p_work_modes TEXT[] DEFAULT NULL, p_include_unknown BOOLEAN DEFAULT false, ",
            "active_posting_count, new_posting_count, closed_posting_count, salary_disclosed_count",
        ),
        (
            "occupation_demand_v1",
            "occupation",
            "occupation_ids",
            "occupation_id UUID, occupation_name TEXT, occupation_code TEXT, taxonomy_version TEXT",
            "occupation_id, occupation_name, occupation_code, taxonomy_version",
            "p_include_unknown BOOLEAN DEFAULT false, ",
            "active_posting_count, new_posting_count, closed_posting_count, salary_disclosed_count, remote_posting_count",
        ),
        (
            "skill_demand_v1",
            "skill",
            "skill_ids",
            "skill_id UUID, skill_name TEXT, skill_code TEXT, skill_type TEXT, taxonomy_version TEXT, requirement_type TEXT",
            "skill_id, skill_name, skill_code, skill_type, taxonomy_version, requirement_type",
            "p_requirement_types TEXT[] DEFAULT NULL, ",
            "active_posting_count, new_posting_count, closed_posting_count, company_count, occupation_count",
        ),
    )
    for name, view_prefix, ids_name, dimension_returns, dimensions, extra, metrics in definitions:
        view_name = (
            f"v_{view_prefix}_hiring_daily"
            if view_prefix == "company"
            else f"v_{view_prefix}_demand_daily"
        )
        filters = ""
        if view_prefix == "location":
            filters = "AND (p_work_modes IS NULL OR view.work_mode=ANY(p_work_modes)) AND (p_include_unknown OR view.location_id IS NOT NULL)"
        elif view_prefix == "occupation":
            filters = "AND (p_include_unknown OR view.occupation_id IS NOT NULL)"
        elif view_prefix == "skill":
            filters = "AND (p_requirement_types IS NULL OR view.requirement_type=ANY(p_requirement_types))"
        order_suffix = ""
        if view_prefix == "location":
            order_suffix = ", view.work_mode"
        elif view_prefix == "skill":
            order_suffix = ", view.requirement_type"
        op.execute(
            f"""
            CREATE FUNCTION api.{name}(
              p_start_date DATE DEFAULT current_date - 30, p_end_date DATE DEFAULT current_date,
              p_source_ids UUID[] DEFAULT NULL, p_{ids_name} UUID[] DEFAULT NULL,
              {extra}p_limit INTEGER DEFAULT 100, p_offset INTEGER DEFAULT 0)
            RETURNS TABLE (metric_date DATE, source_id UUID, source_slug TEXT,
              {dimension_returns}, {", ".join(metric + " BIGINT" for metric in metrics.split(", "))},
              calculation_version TEXT, calculated_at TIMESTAMPTZ)
            LANGUAGE plpgsql SECURITY DEFINER STABLE
            SET search_path = pg_catalog, api, serving AS $$ BEGIN {common}
              IF p_limit IS NULL OR p_offset IS NULL
                 OR p_limit NOT BETWEEN 1 AND 1000 OR p_offset NOT BETWEEN 0 AND 5000 THEN
                RAISE EXCEPTION 'invalid pagination' USING ERRCODE='22023'; END IF;
              RETURN QUERY SELECT view.metric_date, view.source_id, view.source_slug,
                {", ".join("view." + item.strip() for item in dimensions.split(","))},
                {", ".join("view." + item.strip() for item in metrics.split(","))},
                view.calculation_version::text, view.calculated_at
              FROM serving.{view_name} AS view
              WHERE view.metric_date BETWEEN p_start_date AND p_end_date
                AND (p_source_ids IS NULL OR view.source_id=ANY(p_source_ids))
                AND (p_{ids_name} IS NULL OR view.{view_prefix}_id=ANY(p_{ids_name}))
                {filters}
              ORDER BY view.metric_date, view.source_id,
                       view.{view_prefix}_id NULLS LAST{order_suffix}
              LIMIT p_limit OFFSET p_offset; END; $$
            """
        )
    op.execute(
        f"""
        CREATE FUNCTION api.salary_metrics_v1(
          p_start_date DATE DEFAULT current_date - 30, p_end_date DATE DEFAULT current_date,
          p_source_ids UUID[] DEFAULT NULL, p_occupation_ids UUID[] DEFAULT NULL,
          p_location_ids UUID[] DEFAULT NULL, p_currency TEXT DEFAULT NULL,
          p_period TEXT DEFAULT NULL, p_tax_basis TEXT DEFAULT NULL,
          p_include_unknown_dimensions BOOLEAN DEFAULT false,
          p_limit INTEGER DEFAULT 100, p_offset INTEGER DEFAULT 0)
        RETURNS TABLE (
          metric_date DATE, source_id UUID, source_slug TEXT,
          occupation_id UUID, occupation_name TEXT, location_id UUID,
          location_label TEXT, currency TEXT, period TEXT, tax_basis TEXT,
          disclosed_salary_count BIGINT, estimated_salary_count BIGINT,
          negotiable_salary_count BIGINT, amount_min_average NUMERIC,
          amount_max_average NUMERIC, amount_exact_average NUMERIC,
          normalized_monthly_min_average NUMERIC,
          normalized_monthly_max_average NUMERIC,
          normalized_annual_min_average NUMERIC,
          normalized_annual_max_average NUMERIC,
          normalized_monthly_min_median NUMERIC,
          normalized_monthly_max_median NUMERIC,
          normalized_annual_min_median NUMERIC,
          normalized_annual_max_median NUMERIC,
          calculation_version TEXT, calculated_at TIMESTAMPTZ)
        LANGUAGE plpgsql SECURITY DEFINER STABLE
        SET search_path = pg_catalog, api, serving AS $$ BEGIN {common}
          IF p_limit IS NULL OR p_offset IS NULL
             OR p_limit NOT BETWEEN 1 AND 1000 OR p_offset NOT BETWEEN 0 AND 5000 THEN
            RAISE EXCEPTION 'invalid pagination' USING ERRCODE='22023'; END IF;
          RETURN QUERY SELECT view.metric_date, view.source_id, view.source_slug,
            view.occupation_id, view.occupation_name, view.location_id,
            view.location_label, view.currency, view.period, view.tax_basis,
            view.disclosed_salary_count, view.estimated_salary_count,
            view.negotiable_salary_count, view.amount_min_average,
            view.amount_max_average, view.amount_exact_average,
            view.normalized_monthly_min_average, view.normalized_monthly_max_average,
            view.normalized_annual_min_average, view.normalized_annual_max_average,
            view.normalized_monthly_min_median, view.normalized_monthly_max_median,
            view.normalized_annual_min_median, view.normalized_annual_max_median,
            view.calculation_version::text, view.calculated_at
          FROM serving.v_salary_metrics_daily AS view
          WHERE view.metric_date BETWEEN p_start_date AND p_end_date
            AND (p_source_ids IS NULL OR view.source_id=ANY(p_source_ids))
            AND (p_occupation_ids IS NULL OR view.occupation_id=ANY(p_occupation_ids))
            AND (p_location_ids IS NULL OR view.location_id=ANY(p_location_ids))
            AND (p_currency IS NULL OR view.currency=p_currency)
            AND (p_period IS NULL OR view.period=p_period)
            AND (p_tax_basis IS NULL OR view.tax_basis=p_tax_basis)
            AND (p_include_unknown_dimensions OR
                 (view.occupation_id IS NOT NULL AND view.location_id IS NOT NULL))
          ORDER BY view.metric_date, view.source_id, view.occupation_id NULLS LAST,
                   view.location_id NULLS LAST, view.currency, view.period, view.tax_basis
          LIMIT p_limit OFFSET p_offset; END; $$
        """
    )


def _function_signatures() -> tuple[str, ...]:
    return (
        "api.search_jobs_v1(text,uuid[],uuid[],uuid[],uuid[],uuid[],text[],text[],text[],text[],timestamptz,text,text,text,numeric,numeric,text,integer,integer)",
        "api.get_job_v1(uuid)",
        "api.market_overview_v1(date,date,uuid[],text[],text[],text[])",
        "api.company_hiring_v1(date,date,uuid[],uuid[],integer,integer)",
        "api.location_demand_v1(date,date,uuid[],uuid[],text[],boolean,integer,integer)",
        "api.occupation_demand_v1(date,date,uuid[],uuid[],boolean,integer,integer)",
        "api.skill_demand_v1(date,date,uuid[],uuid[],text[],integer,integer)",
        "api.salary_metrics_v1(date,date,uuid[],uuid[],uuid[],text,text,text,boolean,integer,integer)",
    )


def _apply_grants() -> None:
    op.execute(f"GRANT USAGE ON SCHEMA api TO {CLIENT_ROLES}")
    op.execute("GRANT USAGE ON SCHEMA serving TO service_role")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA serving FROM PUBLIC, anon, authenticated")
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON serving.refresh_runs, "
        "serving.job_search_documents TO service_role"
    )
    op.execute("GRANT SELECT ON serving.job_search_salary_offers TO service_role")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA serving TO service_role")
    for view_name in (
        "v_current_job_cards",
        "v_market_overview_daily",
        "v_company_hiring_daily",
        "v_location_demand_daily",
        "v_occupation_demand_daily",
        "v_skill_demand_daily",
        "v_salary_metrics_daily",
    ):
        op.execute(
            f"REVOKE ALL ON serving.{view_name} FROM PUBLIC, anon, authenticated, service_role"
        )
    for signature in _function_signatures():
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {signature} TO {CLIENT_ROLES}")


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER trg_observation_descriptions__serving_redaction "
        "ON history.observation_descriptions"
    )
    for table_name in (
        "observation_descriptions",
        "observation_locations",
        "observation_salaries",
        "observation_skills",
        "observation_occupations",
    ):
        op.execute(f"DROP TRIGGER trg_{table_name}__serving_finalized ON history.{table_name}")
    op.execute("DROP FUNCTION serving.invalidate_redacted_description_document()")
    op.execute("DROP FUNCTION serving.prevent_served_observation_child_insert()")
    for signature in _function_signatures():
        op.execute(f"REVOKE ALL ON FUNCTION {signature} FROM {CLIENT_ROLES}")
        op.execute(f"DROP FUNCTION {signature}")
    for view_name in (
        "v_salary_metrics_daily",
        "v_skill_demand_daily",
        "v_occupation_demand_daily",
        "v_location_demand_daily",
        "v_company_hiring_daily",
        "v_market_overview_daily",
        "v_current_job_cards",
    ):
        op.execute(f"DROP VIEW serving.{view_name}")
    op.execute("DROP TRIGGER trg_serving_refresh_runs__lineage_immutable ON serving.refresh_runs")
    op.execute(
        "DROP TRIGGER trg_job_search_salary_offers__validate ON serving.job_search_salary_offers"
    )
    op.execute(
        "DROP TRIGGER trg_job_search_documents__rebuild_salaries ON serving.job_search_documents"
    )
    op.execute("DROP TRIGGER trg_job_search_documents__build ON serving.job_search_documents")
    op.execute("DROP FUNCTION serving.prevent_refresh_lineage_mutation()")
    op.execute("DROP FUNCTION serving.rebuild_job_search_salary_offers()")
    op.execute("DROP FUNCTION serving.validate_search_salary_offer()")
    op.execute("DROP FUNCTION serving.build_job_search_document()")
    op.execute("DROP TABLE serving.job_search_salary_offers")
    op.execute("DROP TABLE serving.job_search_documents")
    op.execute("DROP TABLE serving.refresh_runs")
    op.execute("DROP SCHEMA api")
    op.execute("DROP SCHEMA serving")
