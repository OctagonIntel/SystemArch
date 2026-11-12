# ADR-006: Row filtering

Status: Accepted, 2026-11-12

## Context

Sales is split by region. EU sales should only see EU customers and deals. Analysts, finance and support see everything.

## Options

RLS where the role decides the region. RLS reading a session variable like `app.region`. Or a view per region.

## Decision

RLS by role. Tables under `row_filters` in the policy get RLS, and every role reading one must declare `regions`, or the policy won't load. Each role gets its own policy per table.

## Reasoning

The region should come from who you are, not from something you can set. With a session variable, anyone who can run `SET` picks their own region. Views per region multiply with every new region. Per-role policies also show up in `pg_policies`, which keeps the drift check simple.

## Trade-offs

Someone in two regional groups sees both, because policies add up. That's right for a global sales lead, but it means group membership needs review (Phase 4). The table owner skips RLS, see ADR-014.

## How I know it works

Sofia (sales_eu) sees only EU. Daniel (sales_eu and sales_us) sees EU and US. Amara (analyst) sees all three.
