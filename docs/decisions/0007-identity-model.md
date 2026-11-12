# ADR-007: Identity model

Status: Accepted, 2026-11-12

## Context

Access has to land on people, and the logs need to say which person did something, not just which team.

## Options

Group roles that log in directly. Group roles plus a few named logins. Or group roles plus a file that stands in for an identity provider export.

## Decision

Groups plus a fake IdP export. Groups live in `access.yaml` and can't log in. `people.yaml` lists each person and their groups, and each person gets their own login with no direct grants. Removing someone disables their login but keeps the role for the audit trail.

## Reasoning

That's how it works in real companies: people get access through groups managed in the IdP, and nobody grants to individuals. A separate people file keeps "who is in which group" apart from "what a group can do", which is exactly what an access review asks about.

## Trade-offs

The file is hand-written here. In a real setup it would be synced from the IdP. People can only join human groups, never service accounts, and the loader rejects anything else.

## How I know it works

Eleven people exist as their own logins, and every access check runs as a person.
