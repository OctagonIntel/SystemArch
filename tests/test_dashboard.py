"""The dashboard end to end: sign in as real people, ask, approve, end (ADR-009)."""
import os
import re

import pytest
from psycopg import sql

from common.db import password_var
from dashboard.app import app

TAG = "[test] "


@pytest.fixture(autouse=True)
def cleanup(admin, policy):
    yield
    admin.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(policy.owner)))
    try:
        admin.execute("update governance.access_requests set expires_at = now() "
                      "where reason like %s and status = 'approved'", (TAG + "%",))
        admin.execute("select governance.expire_access()")
        admin.execute("delete from governance.access_requests where reason like %s", (TAG + "%",))
    finally:
        admin.execute("RESET ROLE")


def sign_in(login):
    client = app.test_client()
    page = client.post("/sign-in", data={"login": login, "password": os.environ[password_var(login)]},
                       follow_redirects=True)
    assert page.status_code == 200 and b"My access" in page.data
    csrf = re.search(rb'name="csrf" value="([^"]+)"', client.get("/").data)[1].decode()
    return client, csrf


def test_wrong_password_is_refused():
    page = app.test_client().post("/sign-in", data={"login": "sofia_marchetti", "password": "nope"}, follow_redirects=True)
    assert b"Wrong login or password" in page.data


def test_ask_approve_and_end(admin, policy):
    sofia, s_csrf = sign_in("sofia_marchetti")
    page = sofia.post("/request", data={"csrf": s_csrf, "group": "support", "reason": TAG + "covering the help desk",
                                        "days": "7"}, follow_redirects=True)
    assert b"An approver will decide" in page.data and b"pending" in page.data

    hannah, h_csrf = sign_in("hannah_berg")
    page = hannah.get("/approvals")
    assert b"covering the help desk" in page.data
    rid = re.search(rb'action="/decide/(\d+)"', page.data)[1].decode()
    page = hannah.post(f"/decide/{rid}", data={"csrf": h_csrf, "decision": "approve"}, follow_redirects=True)
    assert b"They have access now" in page.data

    page = sofia.get("/")
    assert b"marts.fct_tickets" in page.data and b"until" in page.data

    page = sofia.post(f"/end/{rid}", data={"csrf": s_csrf}, follow_redirects=True)
    assert b"Access ended" in page.data and b"marts.fct_tickets" not in page.data


def test_database_refusals_are_shown():
    sofia, csrf = sign_in("sofia_marchetti")
    page = sofia.post("/request", data={"csrf": csrf, "group": "sales_us", "reason": "short", "days": "5"},
                      follow_redirects=True)
    assert b"at least 10 characters" in page.data


def test_forms_need_the_csrf_token():
    sofia, _ = sign_in("sofia_marchetti")
    assert sofia.post("/request", data={"group": "support", "reason": TAG + "no token here", "days": "5"}).status_code == 400


def test_only_the_auditor_sees_history():
    sofia, _ = sign_in("sofia_marchetti")
    assert sofia.get("/history").status_code == 403
    noah, _ = sign_in("noah_clarke")
    assert noah.get("/history").status_code == 200
