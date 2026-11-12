# Decision log

Every real decision in this project gets an ADR here, using [the template](0000-template.md).

| # | Decision | Where it landed |
|---|---|---|
| [001](0001-where-the-warehouse-runs.md) | Where the warehouse runs | Supabase for dev, postgres:17 in CI |
| 002 | Warehouse vs production DB | not yet |
| [003](0003-layering-model.md) | Layering model | raw / staging / marts |
| [004](0004-enforcement-point.md) | Enforcement point | in the database, no app layer |
| [005](0005-column-protection.md) | Column protection | PII hashed in marts, clear text in marts_restricted by clearance |
| [006](0006-row-filtering.md) | Row filtering | RLS, regions set per role |
| [007](0007-identity-model.md) | Identity model | group roles plus a fake IdP export of people |
| [008](0008-policy-as-code-format.md) | Policy as code format | YAML + Python generator |
| 009 | Who approves access | not yet |
| 010 | Logging | not yet |
| 011 | Break-glass | not yet |
| [012](0012-service-accounts.md) | Service accounts | one per purpose, passwords in .env, rotate on demand |
| [013](0013-pii-classification.md) | What counts as PII | four levels: public, internal, confidential, restricted |
| [014](0014-marts-ownership.md) | Who owns the tables dbt builds | svc_transform, access re-applied by a dbt post-hook |
| [015](0015-proving-access.md) | How access is proven | hand-written cases + generated sweep, drift check, required CI |

Smaller tooling choices that didn't need an ADR: `just` as the task runner because Windows has no make, and pip with a pinned requirements.txt.
