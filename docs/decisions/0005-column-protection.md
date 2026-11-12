# ADR-005: Column protection

Status: Accepted, 2026-11-12

## Context

Some columns are personal: names, emails, phones, salaries, birth dates, national IDs. Analysts need the tables but not those values. HR, payroll and finance need some of them for real.

## Options

Masking views per audience. Column grants on the table. Hashing PII in dbt. Or column grants for some roles plus masking views for the rest.

## Decision

Hash in dbt. Each table with personal data is built twice: `marts_restricted` keeps real values behind column grants, and `marts` has the same rows with every non-public column hashed. The hash is salted, and nobody can read the salt or call the hash function, so you can't hash a guess and compare.

## Reasoning

I'd rather the sensitive values not be in the tables most people read at all. A masking view still sits on top of the real data, and one bad grant on the base table undoes it. With hashing, `marts` simply doesn't contain the values, and hashes still join and count, so analysts lose nothing they need.

## Trade-offs

Hashes are unreadable, not partly masked. Hashed salaries are useless for sums, so totals live in `agg_salary_by_department`. The data is stored twice, which is fine at this size. A new personal column that isn't classified would land in `marts` in clear text, so Phase 3 tests that every column has a level.

## How I know it works

An analyst gets a hash for an email and is denied on `marts_restricted`. Finance reads salary but not national ID. `svc_transform` can't read the salt.
