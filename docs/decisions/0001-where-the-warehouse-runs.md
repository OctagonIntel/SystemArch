# ADR-001: Where the warehouse runs

Status: Accepted, 2026-11-12

## Context

I need a real Postgres with roles, column grants and RLS, and ideally pgaudit for the logging part later. My laptop doesn't have Docker, and I wanted to get going without fighting an install.

## Options

I looked at four: Docker Desktop locally, Neon, Supabase, or installing Postgres straight onto Windows. Docker would match CI exactly and give me full superuser, but needs WSL2 and admin rights. Neon is easy but limits superuser and pgaudit. A native install works but is the hardest for anyone else to reproduce.

## Decision

Supabase free tier for dev and demos (Ireland region), and a plain postgres:17 container in GitHub Actions for CI. The brief said Postgres 16, but Supabase came up on 17.11, so CI runs 17 too and the versions match.

## Reasoning

Local Docker would have matched CI most closely, but it needs admin rights and WSL2, which I don't have on this PC. Native Postgres on Windows can't be reproduced from a clean clone and behaves differently from the Linux container CI uses. That left the hosted options. I chose Supabase over Neon because ADR-010 relies on pgaudit. Supabase supports it, and I confirmed that on first connection, while Neon limits it and restricts superuser access further. I've also used Supabase before in projects and apps I've built, so I know its quirks.

## Trade-offs

Supabase isn't vanilla Postgres. It comes with its own roles (anon, authenticated, service_role and so on) and schemas like auth and storage, so the drift check will have to ignore anything the policy doesn't own. The postgres user can create roles but isn't a true superuser, which might limit some pgaudit settings. Connections go through the session pooler because the direct connection is IPv6 only. The free project also pauses after about a week idle, so I need to wake it up before a demo, and none of this works offline.

Running CI on plain Postgres is how I keep myself honest here. If the same policy and tests pass on both, nothing depends on Supabase quirks.

## How I know it works

`just up` connects and reports the version and whether we can create roles. The first run showed Postgres 17.11, CREATEROLE true, superuser false, pgaudit available.
