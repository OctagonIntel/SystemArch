"""Access requests (ADR-009), run as the real people. Each test cleans up its own requests,
so the rest of the suite sees people.yaml again."""
import psycopg
import pytest

from common.db import as_role, connect_as
from drift.check import find_drift
from conftest import TAG

pytestmark = pytest.mark.usefixtures("clean_requests")


@pytest.fixture
def people():
    conns = {}

    def get(login):
        if login not in conns:
            conns[login] = connect_as(login, autocommit=True)
        return conns[login]

    yield get
    for c in conns.values():
        c.close()


def call(conn, query, *params):
    return conn.execute(query, params).fetchone()[0]


def regions(conn):
    return {r[0] for r in conn.execute("select distinct region from marts.dim_customer").fetchall()}


def test_request_approve_and_revoke(people, admin, policy):
    sofia, daniel = people("sofia_marchetti"), people("daniel_reyes")
    assert regions(sofia) == {"EU"}

    rid = call(sofia, "select governance.request_access('sales_us', %s, 30)", TAG + "covering the US team in December")
    assert regions(sofia) == {"EU"}, "nothing changes until it's approved"

    assert call(daniel, "select governance.decide_request(%s, true)", rid) == "approved"
    assert regions(sofia) == {"EU", "US"}
    assert not find_drift(admin, policy), "an approved request is expected access, not drift"

    daniel.execute("select governance.revoke_access(%s, 'cover finished')", (rid,))
    assert regions(sofia) == {"EU"}
    status = sofia.execute("select status from governance.my_requests() where id = %s", (rid,)).fetchone()[0]
    assert status == "revoked"


def test_access_ends_on_its_own(people, admin, policy):
    sofia, daniel = people("sofia_marchetti"), people("daniel_reyes")
    rid = call(sofia, "select governance.request_access('sales_apac', %s, 1)", TAG + "one day of APAC cover")
    daniel.execute("select governance.decide_request(%s, true)", (rid,))
    assert "APAC" in regions(sofia)

    with as_role(admin, policy.owner):  # pretend the day is over
        admin.execute("update governance.access_requests set expires_at = now() - interval '1 minute' where id = %s", (rid,))

    rows = sofia.execute("select status from governance.my_requests() where id = %s", (rid,)).fetchall()
    assert rows == [("expired",)]
    assert regions(sofia) == {"EU"}


def test_reject_needs_a_reason(people):
    sofia, daniel = people("sofia_marchetti"), people("daniel_reyes")
    rid = call(sofia, "select governance.request_access('sales_us', %s, 10)", TAG + "would like to see US deals")
    with pytest.raises(psycopg.errors.RaiseException, match="why it's rejected"):
        daniel.execute("select governance.decide_request(%s, false)", (rid,))
    assert call(daniel, "select governance.decide_request(%s, false, 'ask your manager first')", rid) == "rejected"


@pytest.mark.parametrize("who, sql_text, error", [
    # Only the group's approvers decide, and never on their own request
    ("mia_tanaka", "select governance.decide_request({rid}, true)", psycopg.errors.InsufficientPrivilege),
    ("sofia_marchetti", "select governance.decide_request({rid}, true)", psycopg.errors.InsufficientPrivilege),
    # Service accounts can't use requests at all
    ("svc_ingest_hr", "select governance.decide_request({rid}, true)", psycopg.errors.InsufficientPrivilege),
    # Only the auditor reads the whole history
    ("sofia_marchetti", "select count(*) from governance.all_requests()", psycopg.errors.InsufficientPrivilege),
])
def test_who_can_decide(people, who, sql_text, error):
    rid = call(people("sofia_marchetti"), "select governance.request_access('sales_us', %s, 10)", TAG + "who can decide this")
    with pytest.raises(error):
        people(who).execute(sql_text.format(rid=int(rid)))


def test_nobody_approves_their_own_request(people):
    daniel = people("daniel_reyes")  # approves sales groups, and asks for one himself
    rid = call(daniel, "select governance.request_access('sales_apac', %s, 10)", TAG + "APAC pipeline review")
    with pytest.raises(psycopg.errors.InsufficientPrivilege, match="own request"):
        daniel.execute("select governance.decide_request(%s, true)", (rid,))
    daniel.execute("select governance.cancel_request(%s)", (rid,))


@pytest.mark.parametrize("group, days, reason, error", [
    ("sales_us", 91, "longer than the group allows", "1 to 90 days"),
    ("sales_us", 10, "short", "at least 10 characters"),
    ("sales_eu", 10, "already in this group", "already have"),
    ("auditor", 10, "auditor can't be requested", "pull request"),
])
def test_request_rules(people, group, days, reason, error):
    with pytest.raises(psycopg.Error, match=error):
        people("sofia_marchetti").execute("select governance.request_access(%s, %s, %s)", (group, TAG + reason if len(reason) > 5 else reason, days))


def test_the_auditor_sees_the_history(people):
    rid = call(people("sofia_marchetti"), "select governance.request_access('support', %s, 5)", TAG + "helping with a ticket backlog")
    ids = {r[0] for r in people("noah_clarke").execute("select id from governance.all_requests()").fetchall()}
    assert rid in ids
