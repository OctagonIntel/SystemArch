-- Policy rules as data, and the functions that enforce them on dbt-built tables.
-- Runs as the owner. apply-policy refills the rule tables each run.

CREATE TABLE IF NOT EXISTS governance.managed_roles (
    role_name text PRIMARY KEY
);

-- table_name '*' = whole schema. clearance_rank caps visible columns. regions '{*}' = all.
CREATE TABLE IF NOT EXISTS governance.table_access (
    role_name      text   NOT NULL,
    schema_name    text   NOT NULL,
    table_name     text   NOT NULL,
    privileges     text[] NOT NULL,
    clearance_rank int,
    regions        text[],
    PRIMARY KEY (role_name, schema_name, table_name)
);

CREATE TABLE IF NOT EXISTS governance.column_classification (
    table_name  text NOT NULL,
    column_name text NOT NULL,
    level       text NOT NULL,
    level_rank  int  NOT NULL,
    PRIMARY KEY (table_name, column_name)
);

CREATE TABLE IF NOT EXISTS governance.row_filters (
    schema_name text NOT NULL,
    table_name  text NOT NULL,
    column_name text NOT NULL,
    PRIMARY KEY (schema_name, table_name)
);

-- Nobody can read the salt. Without it, hashes can't be brute-forced from guesses.
CREATE TABLE IF NOT EXISTS governance.pii_salt (
    id   boolean PRIMARY KEY DEFAULT true CHECK (id),
    salt text NOT NULL
);
INSERT INTO governance.pii_salt (salt)
SELECT replace(gen_random_uuid()::text || gen_random_uuid()::text, '-', '')
WHERE NOT EXISTS (SELECT 1 FROM governance.pii_salt);
REVOKE ALL ON governance.pii_salt FROM PUBLIC;

-- Salted SHA-256, 16 chars. Same input, same token, so joins still work.
CREATE OR REPLACE FUNCTION governance.pii_hash(value text)
RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog
AS $$
    SELECT CASE WHEN value IS NULL THEN NULL
           ELSE left(encode(sha256(convert_to((SELECT salt FROM governance.pii_salt) || value, 'UTF8')), 'hex'), 16)
           END
$$;
REVOKE ALL ON FUNCTION governance.pii_hash(text) FROM PUBLIC;

-- Wipes all grants and RLS policies on a table, then applies the rules. Caller must own it.
-- Called by the dbt post-hook and by apply-policy (ADR-014).
CREATE OR REPLACE FUNCTION governance.apply_access(target regclass)
RETURNS void
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    s text; n text; tbl_owner name; filter_col text; cols text; r record;
BEGIN
    SELECT c.relnamespace::regnamespace::text, c.relname, pg_get_userbyid(c.relowner)
      INTO s, n, tbl_owner
      FROM pg_class c WHERE c.oid = target;

    EXECUTE format('REVOKE ALL ON %s FROM PUBLIC', target);
    FOR r IN SELECT role_name FROM governance.managed_roles WHERE role_name <> tbl_owner LOOP
        EXECUTE format('REVOKE ALL ON %s FROM %I', target, r.role_name);
    END LOOP;
    FOR r IN SELECT polname FROM pg_policy WHERE polrelid = target LOOP
        EXECUTE format('DROP POLICY %I ON %s', r.polname, target);
    END LOOP;

    FOR r IN SELECT * FROM governance.table_access a
             WHERE a.schema_name = s AND a.table_name IN (n, '*') AND a.role_name <> tbl_owner LOOP
        IF r.clearance_rank IS NULL THEN
            EXECUTE format('GRANT %s ON %s TO %I', array_to_string(r.privileges, ', '), target, r.role_name);
        ELSE
            SELECT string_agg(quote_ident(a.attname), ', ' ORDER BY a.attnum) INTO cols
              FROM pg_attribute a
              LEFT JOIN governance.column_classification c ON c.table_name = n AND c.column_name = a.attname
             WHERE a.attrelid = target AND a.attnum > 0 AND NOT a.attisdropped
               AND coalesce(c.level_rank, 0) <= r.clearance_rank;
            EXECUTE format('GRANT SELECT (%s) ON %s TO %I', cols, target, r.role_name);
        END IF;
    END LOOP;

    SELECT column_name INTO filter_col FROM governance.row_filters WHERE schema_name = s AND table_name = n;
    IF filter_col IS NULL THEN
        EXECUTE format('ALTER TABLE %s DISABLE ROW LEVEL SECURITY', target);
        RETURN;
    END IF;

    -- RLS denies by default: SELECT without a policy returns no rows.
    EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', target);
    FOR r IN SELECT a.role_name, a.regions FROM governance.table_access a
             WHERE a.schema_name = s AND a.table_name IN (n, '*') AND 'SELECT' = ANY (a.privileges)
               AND a.role_name <> tbl_owner LOOP
        EXECUTE format('CREATE POLICY %I ON %s FOR SELECT TO %I USING (%s)',
            r.role_name || '_rows', target, r.role_name,
            CASE WHEN r.regions IS NULL OR r.regions = '{}' THEN 'false'
                 WHEN '*' = ANY (r.regions) THEN 'true'
                 ELSE format('%I = ANY (%L::text[])', filter_col, r.regions) END);
    END LOOP;
END
$$;
REVOKE ALL ON FUNCTION governance.apply_access(regclass) FROM PUBLIC;
