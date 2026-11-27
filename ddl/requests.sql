-- ADR-009. Access requests: who is in a group can change without a pull request.
-- A person asks, one of the group's approvers decides, and the grant ends on its own.
-- The rules live here, in the database, so the dashboard is only a screen on top (ADR-004).
-- Every function checks session_user, the login that connected, which can't be faked.
-- They run as the owner, which holds ADMIN on the people groups and nothing more (roles.sql.j2).

-- Refilled by apply-policy from access.yaml and people.yaml.
CREATE TABLE IF NOT EXISTS governance.request_rules (
    group_name text   PRIMARY KEY,
    purpose    text   NOT NULL,
    max_days   int    NOT NULL CHECK (max_days > 0),
    approvers  text[] NOT NULL
);

CREATE TABLE IF NOT EXISTS governance.people (
    login      text   PRIMARY KEY,
    name       text   NOT NULL,
    department text   NOT NULL,
    groups     text[] NOT NULL  -- from people.yaml and `everyone`, never requested ones
);

-- History. Nothing deletes from it, and only the functions below change a status.
CREATE TABLE IF NOT EXISTS governance.access_requests (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    login        text NOT NULL,
    group_name   text NOT NULL,
    reason       text NOT NULL,
    days         int  NOT NULL CHECK (days > 0),
    status       text NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'approved', 'rejected', 'cancelled', 'expired', 'revoked')),
    requested_at timestamptz NOT NULL DEFAULT now(),
    decided_by   text,
    decided_at   timestamptz,
    note         text,
    expires_at   timestamptz,
    ended_by     text,
    ended_at     timestamptz
);
-- One open request or grant per person and group.
CREATE UNIQUE INDEX IF NOT EXISTS access_requests_one_open
    ON governance.access_requests (login, group_name) WHERE status IN ('pending', 'approved');

-- The person calling, or an error if they aren't in people.yaml.
CREATE OR REPLACE FUNCTION governance._caller()
RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM governance.people WHERE login = session_user) THEN
        RAISE EXCEPTION 'Only people in people.yaml can use access requests, not %', session_user
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN session_user;
END
$$;

-- Takes a group away unless people.yaml gives it anyway.
CREATE OR REPLACE FUNCTION governance._take_away(p_login text, p_group text)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM governance.people WHERE login = p_login AND p_group = ANY (groups))
       AND pg_has_role(p_login, p_group, 'MEMBER') THEN
        EXECUTE format('REVOKE %I FROM %I', p_group, p_login);
    END IF;
END
$$;

-- Ends every grant past its date, and any held by someone who has left.
-- Runs at the start of every function below, in apply-policy and in `just expire`.
CREATE OR REPLACE FUNCTION governance.expire_access()
RETURNS int
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE r record; n int := 0;
BEGIN
    FOR r IN SELECT a.id, a.login, a.group_name
             FROM governance.access_requests a
             WHERE a.status = 'approved'
               AND (a.expires_at <= now() OR NOT EXISTS (SELECT 1 FROM governance.people p WHERE p.login = a.login))
             FOR UPDATE LOOP
        PERFORM governance._take_away(r.login, r.group_name);
        UPDATE governance.access_requests SET status = 'expired', ended_by = 'expiry', ended_at = now()
         WHERE id = r.id;
        n := n + 1;
    END LOOP;
    RETURN n;
END
$$;

-- Groups the caller can ask for, and whether they already have them.
CREATE OR REPLACE FUNCTION governance.requestable()
RETURNS TABLE (group_name text, purpose text, max_days int, approvers text[], has_it boolean, open_request bigint)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
#variable_conflict use_column
DECLARE me text := governance._caller();
BEGIN
    PERFORM governance.expire_access();
    RETURN QUERY
    SELECT r.group_name, r.purpose, r.max_days,
           array(SELECT p.name FROM governance.people p WHERE p.login = ANY (r.approvers) ORDER BY p.name),
           pg_has_role(me, r.group_name, 'USAGE'),
           (SELECT a.id FROM governance.access_requests a
             WHERE a.login = me AND a.group_name = r.group_name AND a.status IN ('pending', 'approved'))
    FROM governance.request_rules r
    ORDER BY r.group_name;
END
$$;

CREATE OR REPLACE FUNCTION governance.request_access(p_group text, p_reason text, p_days int)
RETURNS bigint
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE me text := governance._caller(); rule governance.request_rules; new_id bigint;
BEGIN
    PERFORM governance.expire_access();
    SELECT * INTO rule FROM governance.request_rules WHERE group_name = p_group;
    IF NOT FOUND THEN
        RAISE EXCEPTION '% can''t be requested here. It changes through people.yaml and a pull request', p_group
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_days IS NULL OR p_days < 1 OR p_days > rule.max_days THEN
        RAISE EXCEPTION '% can be granted for 1 to % days', p_group, rule.max_days;
    END IF;
    IF length(trim(coalesce(p_reason, ''))) < 10 THEN
        RAISE EXCEPTION 'Say why you need it, in at least 10 characters';
    END IF;
    IF pg_has_role(me, p_group, 'USAGE') THEN
        RAISE EXCEPTION 'You already have %', p_group;
    END IF;
    IF EXISTS (SELECT 1 FROM governance.access_requests
                WHERE login = me AND group_name = p_group AND status = 'pending') THEN
        RAISE EXCEPTION 'You already asked for %. It''s waiting for an approver', p_group;
    END IF;
    INSERT INTO governance.access_requests (login, group_name, reason, days)
    VALUES (me, p_group, trim(p_reason), p_days)
    RETURNING id INTO new_id;
    RETURN new_id;
END
$$;

CREATE OR REPLACE FUNCTION governance.cancel_request(p_id bigint)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE me text := governance._caller();
BEGIN
    UPDATE governance.access_requests SET status = 'cancelled', ended_by = me, ended_at = now()
     WHERE id = p_id AND login = me AND status = 'pending';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'Request % isn''t a pending request of yours', p_id;
    END IF;
END
$$;

-- An approver grants or rejects. Only for groups they approve, never their own request.
CREATE OR REPLACE FUNCTION governance.decide_request(p_id bigint, p_approve boolean, p_note text DEFAULT NULL)
RETURNS text
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE me text := governance._caller(); req governance.access_requests; rule governance.request_rules;
BEGIN
    PERFORM governance.expire_access();
    SELECT * INTO req FROM governance.access_requests WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'There is no request %', p_id;
    END IF;
    SELECT * INTO rule FROM governance.request_rules WHERE group_name = req.group_name;
    IF rule.group_name IS NULL OR NOT (me = ANY (rule.approvers)) THEN
        RAISE EXCEPTION 'You don''t approve requests for %', req.group_name USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF req.login = me THEN
        RAISE EXCEPTION 'Nobody approves their own request' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF req.status <> 'pending' THEN
        RAISE EXCEPTION 'Request % is already %', p_id, req.status;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM governance.people WHERE login = req.login) THEN
        RAISE EXCEPTION '% has left, so the request can''t be approved', req.login;
    END IF;

    IF p_approve THEN
        IF req.days > rule.max_days THEN
            RAISE EXCEPTION '% can now be granted for at most % days. Ask for a new request', req.group_name, rule.max_days;
        END IF;
        EXECUTE format('GRANT %I TO %I WITH INHERIT TRUE, SET FALSE', req.group_name, req.login);
        UPDATE governance.access_requests
           SET status = 'approved', decided_by = me, decided_at = now(), note = nullif(trim(p_note), ''),
               expires_at = now() + make_interval(days => req.days)
         WHERE id = p_id;
        RETURN 'approved';
    END IF;

    IF length(trim(coalesce(p_note, ''))) = 0 THEN
        RAISE EXCEPTION 'Say why it''s rejected, so they know what to do instead';
    END IF;
    UPDATE governance.access_requests
       SET status = 'rejected', decided_by = me, decided_at = now(), note = trim(p_note)
     WHERE id = p_id;
    RETURN 'rejected';
END
$$;

-- Ends a grant early. The group's approvers can, and so can the person holding it.
CREATE OR REPLACE FUNCTION governance.revoke_access(p_id bigint, p_note text DEFAULT NULL)
RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE me text := governance._caller(); req governance.access_requests;
BEGIN
    SELECT * INTO req FROM governance.access_requests WHERE id = p_id FOR UPDATE;
    IF NOT FOUND OR req.status <> 'approved' THEN
        RAISE EXCEPTION 'Request % isn''t a running grant', p_id;
    END IF;
    IF req.login <> me AND NOT EXISTS (SELECT 1 FROM governance.request_rules
                                        WHERE group_name = req.group_name AND me = ANY (approvers)) THEN
        RAISE EXCEPTION 'Only the approvers of % or % can end it', req.group_name, req.login
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    PERFORM governance._take_away(req.login, req.group_name);
    UPDATE governance.access_requests
       SET status = 'revoked', ended_by = me, ended_at = now(), note = coalesce(nullif(trim(p_note), ''), note)
     WHERE id = p_id;
END
$$;

-- One view of the history, with names. Each function below filters it for its caller.
CREATE OR REPLACE VIEW governance.request_history AS
SELECT a.id, a.login, coalesce(p.name, a.login) AS name, coalesce(p.department, '') AS department,
       a.group_name, a.reason, a.days, a.status, a.requested_at,
       coalesce(d.name, a.decided_by) AS decided_by, a.decided_at, a.note, a.expires_at,
       coalesce(e.name, a.ended_by) AS ended_by, a.ended_at
FROM governance.access_requests a
LEFT JOIN governance.people p ON p.login = a.login
LEFT JOIN governance.people d ON d.login = a.decided_by
LEFT JOIN governance.people e ON e.login = a.ended_by;
REVOKE ALL ON governance.request_history FROM PUBLIC;

CREATE OR REPLACE FUNCTION governance.my_requests()
RETURNS SETOF governance.request_history
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE me text := governance._caller();
BEGIN
    PERFORM governance.expire_access();
    RETURN QUERY SELECT * FROM governance.request_history h WHERE h.login = me ORDER BY h.requested_at DESC;
END
$$;

-- Pending requests the caller can decide, and running grants they can end.
CREATE OR REPLACE FUNCTION governance.requests_to_decide()
RETURNS SETOF governance.request_history
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
DECLARE me text := governance._caller();
BEGIN
    PERFORM governance.expire_access();
    RETURN QUERY
    SELECT h.* FROM governance.request_history h
    JOIN governance.request_rules r ON r.group_name = h.group_name AND me = ANY (r.approvers)
    WHERE h.status IN ('pending', 'approved')
    ORDER BY h.status DESC, h.requested_at;
END
$$;

-- The whole history, for the auditor.
CREATE OR REPLACE FUNCTION governance.all_requests()
RETURNS SETOF governance.request_history
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    PERFORM governance.expire_access();
    RETURN QUERY SELECT * FROM governance.request_history h ORDER BY h.requested_at DESC;
END
$$;

REVOKE ALL ON FUNCTION governance._caller(), governance._take_away(text, text), governance.expire_access(),
    governance.requestable(), governance.request_access(text, text, int), governance.cancel_request(bigint),
    governance.decide_request(bigint, boolean, text), governance.revoke_access(bigint, text),
    governance.my_requests(), governance.requests_to_decide(), governance.all_requests() FROM PUBLIC;
