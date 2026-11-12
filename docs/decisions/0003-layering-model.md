# ADR-003: Layering model

Status: Accepted, 2026-11-12

## Context

Data comes in from four sources and has to end up as tables people can query. I need layers so cleaning and business logic don't get mixed together, and so I can grant access per layer instead of per table.

## Options

raw / staging / marts is the dbt convention. bronze / silver / gold (medallion) is the same idea with different names and is common in lakehouse setups. I also thought about just raw and marts, but then cleaning and business logic end up in the same models and there's nowhere to keep things only the transform job should see.

## Decision

raw / staging / marts, plus an audit schema for logs. The names say who each layer is for, which makes the policy file read naturally: ingest writes raw, transform owns staging, people read marts.

Raw is all text and append-only. Each load gets a batch ID, and staging takes the newest row per key. Ingest accounts can only insert, so they can't fix or delete anything they've loaded, and raw becomes a history of every load.

## Trade-offs

Raw grows with every load because nothing gets deleted. Fine at this size. At scale I'd partition it by load date and add retention. If I do the AWS version later, the medallion names would match the tooling better, but the layers themselves map one to one.

## How I know it works

`just seed` loads a fresh batch every run. After two runs raw.hr_employees has 480 rows over 2 batches, and marts.dim_employee still has 240.
