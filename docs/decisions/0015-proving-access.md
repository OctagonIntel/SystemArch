# ADR-015: How access is proven

Status: Accepted, 2026-11-12

## Context

A policy file only matters if the database actually does what it says. I need tests that prove it, and a way to spot changes made behind the policy's back.

## Options

Run tests only in a CI container, only against Supabase, or both. Write the expected access by hand, generate it from the policy, or both. Scope the drift check by naming pattern, or by our schemas plus every role the policy manages.

## Decision

- Tests run in CI on a fresh postgres:17 (no secrets), and locally against Supabase with `just test`.
- `tests/cases.yaml` holds hand-written cases, the demo story. A generated sweep checks every login against every table: columns, regions and write rights.
- Access tests log in as the real person or account. Separation of duties and drift read the catalog as admin.
- `just drift` covers our schemas and every role the policy manages, and any grant to an unknown role in our schemas counts.
- CI is a required check on `main`.

## Reasoning

Hand-written cases catch a wrong policy, because a person decided what should happen. The generated sweep catches a database that drifted from the policy, across everything, not just the cases I thought of. Each covers the other's blind spot. Scoping drift by schema instead of name means a rogue role can't hide behind an unexpected name.

## Trade-offs

The suite takes about three minutes against Supabase, mostly network round trips. Supabase's own roles (`supabase_read_only_user`, `supabase_etl_admin`) can read everything through `pg_read_all_data`. They're platform roles I can't remove, so they're listed in the policy and a test fails if a new one appears.

## How I know it works

A hand-made grant giving support salaries fails three tests: the hand-written case, the sweep for Hannah, and drift. `just apply-policy` reverts it.
