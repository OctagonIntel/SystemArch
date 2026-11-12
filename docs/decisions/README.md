# Decision log

Every real decision in this project gets an ADR here, using [the template](0000-template.md). Claude helped me lay out the options. The choices are mine.

| # | Decision | Where it landed |
|---|---|---|
| [001](0001-where-the-warehouse-runs.md) | Where the warehouse runs | Supabase for dev, postgres:17 in CI |
| 002 | Warehouse vs production DB | not yet |
| [003](0003-layering-model.md) | Layering model | raw / staging / marts |
| 004 | Enforcement point | not yet |
| 005 | Column protection | not yet |
| 006 | Row filtering | not yet |
| 007 | Identity model | not yet |
| [008](0008-policy-as-code-format.md) | Policy as code format | YAML + Python generator |
| 009 | Who approves access | not yet |
| 010 | Logging | not yet |
| 011 | Break-glass | not yet |
| [012](0012-service-accounts.md) | Service accounts | one per purpose, passwords in .env, rotate on demand |
| 013 | What counts as PII | not yet |

Smaller tooling choices that didn't need an ADR: `just` as the task runner because Windows has no make, and pip with a pinned requirements.txt.
