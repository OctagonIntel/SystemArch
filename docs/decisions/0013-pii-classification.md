# ADR-013: What counts as PII

Status: Accepted, 2026-11-12

## Context

To hash and grant by sensitivity, every personal column needs a level, and the levels need to mean something consistent.

## Options

A simple PII yes/no flag, which can't treat a salary differently from an email. Three levels (public, internal, restricted). Or four levels in the style of ISO 27001 (public, internal, confidential, restricted).

## Decision

Four levels, set per column in `access.yaml`:

- **public**: fine for anyone with access to the table. IDs, region, department, dates of business events.
- **internal**: identifies a person but does little harm on its own. Names and work email addresses.
- **confidential**: could hurt someone or the business if it leaked. Salary and phone numbers.
- **restricted**: identity theft material. National ID and date of birth.

A role's clearance on a `marts_restricted` table shows it every column at or below that level. HR has restricted. Finance and sales have confidential. Support has internal on tickets and confidential on customers.

## Reasoning

<!-- Matt: why four levels -->

## Trade-offs

Levels are set per column name within a table, so a column keeps its level in every schema the table is built in. Anything not listed is public by default, which is the risky direction. Phase 3 adds a test that fails if a column in `marts_restricted` isn't listed.

## How I know it works

Finance can read salary (confidential) but not national ID (restricted). HR can read both.
