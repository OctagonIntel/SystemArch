# ADR-014: Who owns the tables dbt builds

Status: Accepted, 2026-11-12

## Context

dbt runs as `svc_transform`, so it owns every table it creates. An owner skips grants and RLS. And dbt rebuilds a table by creating a new one and swapping it in, which throws away every grant and RLS policy on the old one.

## Options

A dbt post-hook that re-applies access after each model, with `svc_transform` staying the owner. Handing ownership to `wh_owner` after dbt runs and re-granting from there. Or having dbt create tables as `wh_owner` through `SET ROLE`.

## Decision

The post-hook. apply-policy writes the rules into tables in the `governance` schema, and every model in `marts` and `marts_restricted` ends with `select governance.apply_access(this)`. That function wipes every grant and RLS policy on the table and then applies exactly what the rules say. apply-policy runs the same function on tables that already exist, so a policy change takes effect without a dbt run.

## Reasoning

<!-- Matt: why the post-hook over handing ownership over -->

## Trade-offs

`svc_transform` is still the owner, so whoever holds its password can read every marts table and could grant themselves or others anything. That's the cost of letting dbt manage its own tables. The drift check (Phase 3) is what catches a grant that isn't in the policy, and ADR-012 keeps that password to one purpose.

If a dbt run fails partway, the table that failed keeps its old version and its old grants, since the swap and the post-hook run in the same transaction.

## How I know it works

After `dbt build`, every marts table has exactly the grants and RLS policies the rules describe, without running apply-policy again. The access matrix on the progress page and the smoke test both read the live database.
