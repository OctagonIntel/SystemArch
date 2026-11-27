"""Access dashboard (ADR-009): ask for access, decide requests, see the history.

    python -m dashboard.app          sign in with your own database login
    python -m dashboard.app --demo   pick a person, using the passwords in .env

Only a screen. Every rule (who approves, how long, never your own) is enforced by the
governance functions in the database, which see you as the login you signed in with.
Runs on 127.0.0.1 only.
"""
import argparse
import os
import secrets
from functools import wraps

import psycopg
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for

from common.db import connect_as, password_var
from generator.policy import load_policy

app = Flask(__name__)
app.secret_key = secrets.token_bytes(32)  # new each start, so sign-ins don't outlive the process
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict")

POLICY = load_policy()
PEOPLE = {p.login: p for p in POLICY.people}
GROUPS = {r.name: r for r in POLICY.roles.values() if r.type == "human"}
DEMO = False
_passwords: dict[str, tuple[str, str]] = {}  # session id -> (login, password), kept in memory only


def db() -> psycopg.Connection:
    login, password = _passwords[session["sid"]]
    return connect_as(login, password, autocommit=True)


def query(sql_text, *params):
    with db() as conn:
        cur = conn.execute(sql_text, params)
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def signed_in(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if session.get("sid") not in _passwords:
            return redirect(url_for("sign_in"))
        if request.method == "POST" and request.form.get("csrf") != session.get("csrf"):
            abort(400)
        return view(*args, **kwargs)
    return wrapper


def run(sql_text, *params, ok: str):
    """Calls a governance function and shows the database's own message if it refuses."""
    try:
        with db() as conn:
            conn.execute(sql_text, params)
        flash(ok, "ok")
    except psycopg.Error as e:
        flash(e.diag.message_primary or str(e), "error")


@app.context_processor
def common():
    login = _passwords.get(session.get("sid"), (None,))[0]
    approves = [g.name for g in POLICY.requestable if login in g.request.approvers]
    return {"me": PEOPLE.get(login), "approves": approves, "groups": GROUPS,
            "is_auditor": login is not None and "auditor" in PEOPLE[login].groups, "csrf": session.get("csrf")}


@app.route("/sign-in", methods=["GET", "POST"])
def sign_in():
    if request.method == "POST":
        login = request.form.get("login", "").strip()
        password = request.form.get("password") or (os.environ.get(password_var(login)) if DEMO else None)
        if login not in PEOPLE or not password:
            flash("Unknown login, or no password", "error")
        else:
            try:
                connect_as(login, password).close()
            except (psycopg.Error, RuntimeError, SystemExit):
                flash("Wrong login or password", "error")
            else:
                session.clear()
                session["sid"], session["csrf"] = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
                _passwords[session["sid"]] = (login, password)
                return redirect(url_for("home"))
    return render_template("sign_in.html", demo=DEMO, people=sorted(PEOPLE.values(), key=lambda p: p.name))


@app.post("/sign-out")
def sign_out():
    _passwords.pop(session.get("sid"), None)
    session.clear()
    return redirect(url_for("sign_in"))


@app.route("/")
@signed_in
def home():
    mine = query("select * from governance.my_requests()")
    running = {r["group_name"]: r for r in mine if r["status"] == "approved"}
    tables = query("""
        select n.nspname as schema, c.relname as name,
               count(*) filter (where has_column_privilege(c.oid, a.attnum, 'SELECT')) as readable,
               count(*) as total
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        join pg_attribute a on a.attrelid = c.oid and a.attnum > 0 and not a.attisdropped
        where n.nspname = any(%s) and c.relkind in ('r', 'p', 'v', 'm')
          and has_schema_privilege(n.oid, 'USAGE')
        group by 1, 2
        having count(*) filter (where has_column_privilege(c.oid, a.attnum, 'SELECT')) > 0
        order by 1, 2""", list(POLICY.schemas))
    held = query("""
        select r.rolname as name from pg_roles r
        where pg_has_role(current_user, r.oid, 'USAGE') and r.rolname <> current_user and r.rolname = any(%s)
        order by 1""", list(GROUPS))
    return render_template("home.html", held=[g["name"] for g in held], running=running, tables=tables,
                           mine=mine, requestable=query("select * from governance.requestable()"))


@app.post("/request")
@signed_in
def ask():
    run("select governance.request_access(%s, %s, %s)", request.form["group"], request.form["reason"],
        int(request.form.get("days") or 0), ok=f"Asked for {request.form['group']}. An approver will decide.")
    return redirect(url_for("home"))


@app.post("/cancel/<int:rid>")
@signed_in
def cancel(rid):
    run("select governance.cancel_request(%s)", rid, ok="Request cancelled")
    return redirect(url_for("home"))


@app.post("/end/<int:rid>")
@signed_in
def end(rid):
    run("select governance.revoke_access(%s, %s)", rid, request.form.get("note"), ok="Access ended")
    return redirect(request.referrer or url_for("home"))


@app.route("/approvals")
@signed_in
def approvals():
    rows = query("select * from governance.requests_to_decide()")
    return render_template("approvals.html", pending=[r for r in rows if r["status"] == "pending"],
                           running=[r for r in rows if r["status"] == "approved"])


@app.post("/decide/<int:rid>")
@signed_in
def decide(rid):
    approve = request.form.get("decision") == "approve"
    run("select governance.decide_request(%s, %s, %s)", rid, approve, request.form.get("note"),
        ok="Approved. They have access now." if approve else "Rejected")
    return redirect(url_for("approvals"))


@app.route("/history")
@signed_in
def history():
    try:
        rows = query("select * from governance.all_requests()")
    except psycopg.errors.InsufficientPrivilege:
        abort(403)
    return render_template("history.html", rows=rows)


def main():
    global DEMO
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", action="store_true", help="pick a person instead of typing a password")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    DEMO = args.demo
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
