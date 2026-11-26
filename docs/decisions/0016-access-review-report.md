# ADR-016: Access review report

Status: Accepted, 2026-11-26

## Context

Tests and the drift check prove the database matches the policy, but they only speak up when something is wrong. A periodic access review needs the opposite: a page a manager or auditor can read and sign off on, showing who can see what right now, including what's fine.

## Options

Generate it from the policy alone, read it from the live catalog, or both. Show it as a list per person, a matrix of logins against tables, or a BI dashboard. Publish it as a static file, a hosted page, or a table in the `audit` schema.

## Decision

- `just report` reads the live catalog as admin and writes one self-contained HTML page to `report/out/`. Every cell is compared with what the policy grants, and the drift findings are included.
- `just report --policy-only` renders what the policy grants without a database, for reviewing a policy change in a PR.
- The main view is a matrix: logins down the side, tables across. Each cell shows the most sensitive clear-text level that login can read there, the regions it sees and whether it can write. Below that: every sensitive column with who reads it, a per-login breakdown, and a sign-off block.
- CI runs the report after the tests and keeps it as a build artifact for 30 days.

## Reasoning

The live catalog is the truth an auditor cares about, and the policy is what it's judged against, so the report shows the first and flags anything that differs from the second. Reading privileges with `has_column_privilege` and the RLS policies is a third, independent way of looking, next to the sweep (logs in as each person) and drift (compares ACLs). A test checks all three agree.

A matrix answers "who can see restricted data" at a glance, and the per-login lists are what a manager actually confirms. One static file needs no server, can be attached to an audit ticket, and prints.

## Trade-offs

Levels come from the classification, which is keyed by mart table name. raw and staging aren't classified, so any read there counts as restricted. That's deliberately pessimistic: only `svc_transform` reads them. Hashed columns in `marts` count as public, which follows ADR-005 but leans on the salt staying secret.

The report shows where access comes from per the policy (which group), not the role chain Postgres actually used. If access arrives some other way, the cell is flagged as different from the policy, but the report doesn't say how it got there. `just drift` does.

Sign-off is a printed block, not a recorded approval. Who approves access is ADR-009, still open.

## How I know it works

`tests/test_report.py` checks the policy-only output against known cases, and on a live database requires the report to find no differences that the sweep and drift check didn't. CI runs that live check on every pull request. Still to try by hand: the ADR-015 drill (grant support salaries) should show a red cell for Hannah and a line under Differences.
