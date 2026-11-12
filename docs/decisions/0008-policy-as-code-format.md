# ADR-008: Policy as code format

Status: Accepted, 2026-11-12

## Context

All access has to be declared in one place and turned into SQL automatically, no hand-written grants. I hit this earlier than planned: the ingest scripts in Phase 1 need their service accounts to exist, so I needed the generator before Phase 2.

## Options

A YAML file plus a small Python/Jinja generator. Raw SQL migration files. Or Terraform with the Postgres provider. Terraform is the industry standard for this kind of thing, but it can't really express RLS policies or masking views, so I'd end up with SQL next to it anyway. Plain SQL migrations are easy but they only say what to change, not what the end state should be, so drift detection gets harder.

## Decision

YAML in `policy/access.yaml` and a generator in `generator/`. I started it in Phase 1 with only the service accounts instead of writing a temporary bootstrap script I'd throw away later.

The generator converges rather than adds. For every role in the policy it revokes everything in our schemas and then grants exactly what the YAML says, all in one transaction. Running it twice gives the same result, and anything granted by hand to a policy role gets wiped on the next apply.

A dedicated `wh_owner` role (no login) owns the schemas and raw tables. The admin connection switches to it to create tables and hand out grants, so every grant has `wh_owner` as grantor.

## Trade-offs

I'm maintaining my own generator, so validation and edge cases are on me. The policy loader rejects anything it doesn't understand: unknown privileges, undeclared schemas, service accounts not starting with `svc_`, table grants without schema USAGE. Roles that aren't in the policy at all don't get touched by apply. Catching those is the drift check's job in Phase 3.

## How I know it works

`just plan` prints the SQL without running anything. After `just apply-policy`, connecting as svc_ingest_hr I can insert into raw.hr_employees but can't select from it, can't insert into CRM tables, and can't delete, truncate, drop or create anything. Phase 3 turns that into proper tests.
