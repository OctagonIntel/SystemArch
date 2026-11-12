# ADR-004: Where access is enforced

Status: Accepted, 2026-11-12

## Context

Access rules can live in the database, in an app or API in front of it, or both.

## Options

Database-native grants, column grants and RLS. An app or API layer that filters what users get. Or both.

## Decision

The database. Every rule is a Postgres grant, column grant or RLS policy, generated from the policy file. There's no app layer.

## Reasoning

An app layer only protects people who go through the app. Anyone with a SQL client, a BI tool or a leaked password goes straight past it. In the database, the rule holds no matter how you connect, and the catalog itself becomes the evidence an auditor can check.

## Trade-offs

Postgres grants are coarser than app logic. Anything like "only during business hours" would need more machinery. Platform roles with `pg_read_all_data` skip grants entirely, see ADR-015.

## How I know it works

Every access test connects straight to Postgres as the person, with no app in between, and gets allowed or denied by the database itself.
