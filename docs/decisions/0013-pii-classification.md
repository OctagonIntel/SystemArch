# ADR-013: What counts as PII

Status: Accepted, 2026-11-12

## Context

To hash and grant by sensitivity, each personal column needs a level, and the levels need clear meanings.

## Options

A yes/no PII flag. Three levels. Or four levels, ISO 27001 style.

## Decision

Four levels, set per column in `access.yaml`:

- **public**: anyone with the table. IDs, region, department, business dates.
- **internal**: identifies someone, low harm alone. Names, work emails.
- **confidential**: harmful if leaked. Salary, phone numbers.
- **restricted**: identity theft material. National ID, date of birth.

A role's clearance shows it every column at or below that level. HR and payroll get restricted, finance and sales get confidential, and support gets internal on tickets and confidential on customers.

## Reasoning

A yes/no flag can't tell an email from a national ID, and finance is the proof: they need salaries but not IDs. Four levels match how most companies already label data, so the policy reads naturally to an auditor.

## Trade-offs

Unlisted columns default to public, the risky direction. Phase 3 adds a test that fails on any unclassified column in `marts_restricted`.

## How I know it works

Finance reads salary but not national ID. Payroll and HR read both.
