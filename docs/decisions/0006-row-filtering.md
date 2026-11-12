# ADR-006: Row filtering

Status: Accepted, 2026-11-12

## Context

Sales is split by region. A salesperson in Europe should only see EU customers and deals, while analysts, finance and support see every region.

## Options

Row-level security with a policy per role, where the role decides the region. RLS that reads a session variable like `app.region`, which is flexible but anyone who can run `SET` can change their own region. Or a view per region in its own schema, which has no RLS at all and needs new objects for every new region.

## Decision

RLS, with the region set by the role. In `access.yaml`, a table listed under `row_filters` gets RLS, and every role that reads it has to say `regions: [EU]` or `regions: all`. If a role reads a filtered table without saying which regions, the policy fails to load. `governance.apply_access` turns that into one `CREATE POLICY <role>_rows ... FOR SELECT TO <role>` per role per table.

## Reasoning

<!-- Matt: why region-by-role over a session variable -->

## Trade-offs

A person in two regional groups sees both, because RLS policies add up. That's what I want for a global sales lead, but it means group membership has to be reviewed, which is the access review's job (Phase 4). RLS doesn't apply to the table owner. That's `svc_transform`, see ADR-014.

## How I know it works

Sofia (sales_eu) only gets EU rows from `marts.dim_customer`. Daniel (sales_eu and sales_us) gets EU and US. Amara (analyst) gets all three regions.
