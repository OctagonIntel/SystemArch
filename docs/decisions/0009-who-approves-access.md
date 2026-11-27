# ADR-009: Who approves access

Status: Accepted, 2026-11-27

## Context

Every access change went through a pull request to `policy/`. That's right for changing what a group can do, but most day-to-day requests are "put this person in that group for a while", and nobody should have to edit YAML and wait for a code review for that. It also left no record of who approved a grant, or why.

## Options

Keep pull requests for everything. A GitHub issue form with an approval comment and an Action that applies it. A request table in the warehouse with functions that enforce the rules, and a small dashboard on top. Or hand it to the identity provider's own access requests (Okta, Entra ID).

## Decision

Two kinds of change, two routes:

- **What a group can do** (tables, clearance, regions, classification) stays in `access.yaml`, through a pull request.
- **Who is in a group** can also be requested. A group with `request: {approvers: [...], max_days: N}` in `access.yaml` can be asked for in the dashboard (`just dashboard`). One of its approvers approves or rejects, and an approved grant ends on its own after at most `max_days`.

The rules are enforced in the database, by functions in `ddl/requests.sql`: only people in `people.yaml` can ask, only the group's approvers decide, nobody approves their own request, rejections need a reason, and a grant ends when its date passes or the person leaves. Each function checks `session_user`, the login that connected, so it can't be faked. The owner grants every group membership, from `people.yaml` and from approvals, and holds only ADMIN on the people groups, so it can't use their access.

Every request stays in `governance.access_requests` with who asked, why, who decided and how it ended. The auditor reads the full history.

## Reasoning

ADR-004 puts enforcement in the database, so this does too. The dashboard is only a screen: someone with a SQL client calling the same functions gets exactly the same answers, and a bug in the dashboard can't grant anything the functions wouldn't. An issue form would have needed a bot with rights to change access and a secret in CI. A real IdP is where this belongs in production, but `people.yaml` already stands in for it, and the same split (membership requested, rules reviewed) carries over.

Time limits mean temporary access doesn't depend on someone remembering to remove it.

## Trade-offs

Expiry runs whenever anyone uses a request function, on `just apply-policy` and on `just expire`, not on a timer. A grant can outlive its date until one of those runs. On Supabase, `pg_cron` could run `governance.expire_access()` every hour.

The dashboard signs people in with their warehouse password and keeps it in memory for the session. That's fine for a local demo, not for a shared server, where it would sit behind single sign-on.

`people.yaml` changes still need a pull request. That's deliberate: it stands in for HR's joiner and leaver records.

## How I know it works

`tests/test_access_requests.py` runs the whole flow as real people. Sofia asks for `sales_us`, Daniel approves and she sees US rows, he ends it and she doesn't. A one-day grant expires on its own. It also covers refusals: Mia can't decide sales requests, Daniel can't approve his own, and a service account can't use requests at all. `tests/test_dashboard.py` does the same through the dashboard. The sweep, drift check and report count approved requests as expected access, so a grant made any other way still shows up as drift.
