# ADR-005: Column protection

Status: Accepted, 2026-11-12

## Context

Some columns are personal data: names, emails, phone numbers, salaries, birth dates, national IDs. Analysts need the tables for reporting but shouldn't see those values. HR and finance need some of them in clear text.

## Options

Masking views per audience, which show something like `j***@…` but add an object per table per audience. Column grants on the table itself, which are native and simple but only hide columns, so `SELECT *` fails. Hashing or tokenising PII in dbt so it never sits in the main marts in clear text. Or column grants for the people who need real values plus masking views for everyone else.

## Decision

Hash in dbt. Every table with personal data is built twice. `marts_restricted` holds the clear-text version and `marts` holds the same rows with every column above public (ADR-013) run through `governance.pii_hash`. Who can read which clear-text columns is set by a clearance level per role, and the generator turns it into column grants.

The hash is a salted SHA-256, cut to 16 characters. The salt sits in `governance.pii_salt`, which nobody can read, and the hash function runs as the owner. Nobody else can call it either, so an analyst can't hash a guess and compare.

## Reasoning

<!-- Matt: a line or two on why hashing won for you -->

## Trade-offs

Hashed values can still be joined and counted (same email, same token), which is the point, but they're not readable at all. An analyst sees `a61d9c71b05bf51d` where a masking view would show `j***@example.com`. Salaries become text tokens in `marts`, which is useless for sums, so totals live in `agg_salary_by_department`.

The data is stored twice, which is fine at this size. A new PII column that isn't classified in the policy lands in `marts` in clear text. Phase 3 will add a test that every column in `marts_restricted` is classified, even if only as public.

## How I know it works

Connected as an analyst, `marts.dim_employee.email` comes back hashed and `marts_restricted` is denied. Finance can read `salary_eur` in `marts_restricted.dim_employee` but `national_id` and `SELECT *` are denied. `svc_transform` can't read the salt.
