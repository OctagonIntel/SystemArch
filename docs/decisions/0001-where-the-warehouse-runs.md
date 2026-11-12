# ADR-001: Where the warehouse runs

- **Status:** Proposed *(Matt: change to Accepted once the Reasoning section is in your words)*
- **Date:** 2026-11-12
- **Decider:** Matt

## Context
The warehouse needs real PostgreSQL 16 features: roles, column-level grants, row-level security, and ideally `pgaudit` (ADR-010). It must run from this Windows laptop, where Docker is not installed, and be reproducible from a clean clone. CI (GitHub Actions) needs its own Postgres instance either way.

## Options considered
1. **Local Docker Desktop**: identical to CI, full superuser, works offline. Needs admin rights and WSL2 on this PC.
2. **Neon free tier**: no install. Real Postgres, but superuser is restricted and `pgaudit` is limited.
3. **Supabase free tier**: no install. Real Postgres with RLS and `pgaudit` support. Ships its own built-in roles and schemas.
4. **Native Postgres on Windows**: full control, but setup differs from CI and is harder to reproduce.

## Decision
**Supabase free tier** (project region `eu-west-1`) for development and demos. CI runs a plain `postgres:17` service container.

**Postgres version:** the brief said 16, but Supabase provisions **17** (17.11 at setup). CI matches Supabase's major version, so dev and CI behave the same. Everything the brief relies on (roles, column grants, RLS) is unchanged between 16 and 17.

## Reasoning
Local Docker would have matched CI most closely, but it needs admin rights and WSL2, which I don’t have on my PC. Native Postgres on Windows can’t be reproduced from a clean clone and behaves differently from the Linux container CI uses. That left the hosted options. I chose Supabase over Neon because ADR-010 relies on pgaudit. Supabase supports it, and I confirmed that on first connection, while Neon limits it and restricts superuser access further. Supabase isn’t vanilla Postgres, but CI runs the same policy and tests against a plain postgres:17 container. If anything starts depending on Supabase-specific behaviour, CI will catch it. I also have used Supabase previously in prior projects and Apps that I built.

## Trade-offs accepted
*Drafted by Claude for Matt to confirm, edit or reject:*
- **Dev and CI differ.** Supabase isn't vanilla Postgres. The generator and tests must work on both, so nothing may depend on Supabase-only features.
- **Built-in role noise.** Supabase creates `anon`, `authenticated`, `service_role`, `supabase_*` and others, plus its own schemas (`auth`, `storage`, ...). The drift check (Phase 3) must scope itself to roles and schemas the policy owns, or it will flag things we don't control. That scoping is itself a decision: an allow-list or a naming prefix.
- **Not a true superuser.** The `postgres` user on Supabase can create roles but isn't `SUPERUSER`. Some operations (e.g. certain `pgaudit` settings, `ALTER SYSTEM`) may be unavailable, which affects ADR-010.
- **Connection pooler.** Connect through the *session* pooler (the free-tier direct connection is IPv6-only). Pooler usernames are `role.project_ref`, so each policy role logs in as `svc_ingest_hr.<ref>` etc.
- **Free tier pauses** after about a week of inactivity, so it has to be resumed before demos.
- **Network dependency.** The project can't be worked on offline.

## How we prove it works
- `just up` connects, and reports Postgres version and `CREATEROLE` (`scripts/check_connection.py`).
- CI runs the same `apply-policy` + `test` against `postgres:17`. If both pass, nothing depends on Supabase specifics.
- First run (2026-11-12): `Postgres 17.11 as 'postgres'`, `CREATEROLE: True`, `SUPERUSER: False`, `pgaudit available: True`.
