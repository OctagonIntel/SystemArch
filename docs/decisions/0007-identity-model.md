# ADR-007: Identity model

Status: Accepted, 2026-11-12

## Context

Access has to land on real people, and the audit trail has to say which person did something, not just which team.

## Options

Group roles only, where `analyst` itself logs in. Simplest, but the logs can't tell two analysts apart. Group roles plus a handful of named logins that are members. Or group roles plus a file that stands in for an identity provider export (Okta, Entra ID), which the generator turns into logins.

## Decision

Groups plus a fake IdP export. Group roles (`analyst`, `hr`, `finance`, `sales_eu`, `sales_us`, `sales_apac`, `support`, `auditor`) live in `access.yaml` and can't log in. `policy/people.yaml` lists each person and their groups. apply-policy gives each person a login role (`amara.okafor` becomes `amara_okafor`) that's a member of their groups and holds nothing directly.

Someone who disappears from people.yaml loses their login and every group on the next apply. Their role isn't dropped, so the audit log still has a name to point at.

## Reasoning

<!-- Matt: why the IdP-style file over plain named logins -->

## Trade-offs

people.yaml is hand-written here. In a real company it would be pulled from the IdP on a schedule, and nobody would edit it. People can only be in human groups, never a service account, and the loader rejects anything else. That's one of the separation-of-duties rules Phase 3 tests.

## How I know it works

Ten people from people.yaml exist as login roles with their own passwords. The Phase 2 smoke test ran every check as a person, not as a group.
