# ADR-014: Who owns the tables dbt builds

Status: Accepted, 2026-11-12

## Context

dbt runs as `svc_transform`, so it owns what it builds, and owners skip grants and RLS. Every rebuild also replaces the table, which throws away its grants and policies.

## Options

A dbt post-hook that re-applies access. Handing ownership to `wh_owner` after each run. Or having dbt build as `wh_owner`.

## Decision

The post-hook. The policy's rules live in tables in the `governance` schema, and every marts model ends with `governance.apply_access(this)`, which wipes the table's grants and policies and applies the rules. apply-policy calls the same function, so policy changes land without a dbt run.

## Reasoning

Access is restored in the same transaction that rebuilds the table, so there's never a moment where a table exists without its rules. Changing ownership after the run leaves a gap between the build and the re-grant, and building as `wh_owner` hands dbt the keys to everything.

## Trade-offs

`svc_transform` still owns marts, so its password means full read and the power to grant. The drift check (Phase 3) is the control for that, and ADR-012 keeps the account single-purpose.

## How I know it works

After `dbt build`, every marts table has exactly the grants and policies the rules describe, without running apply-policy.
