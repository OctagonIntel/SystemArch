# Decision log

Every significant choice gets an ADR in this folder, using [`0000-template.md`](0000-template.md). Claude Code may draft context and options. **The decision and the reasoning are Matt's.**

| # | Decision | Status |
|---|---|---|
| [ADR-001](0001-where-the-warehouse-runs.md) | Where does the warehouse run? | Proposed: Supabase |
| ADR-002 | Warehouse vs production DB | Not started |
| ADR-003 | Layering model | Not started |
| ADR-004 | Enforcement point | Not started |
| ADR-005 | Column protection | Not started |
| ADR-006 | Row filtering | Not started |
| ADR-007 | Identity model | Not started |
| ADR-008 | Policy as code format | Not started |
| ADR-009 | Who approves access? | Not started |
| ADR-010 | Logging | Not started |
| ADR-011 | Break-glass | Not started |
| ADR-012 | Service accounts | Not started |
| ADR-013 | What counts as PII here? | Not started |

### Tooling choices (Phase 0, no ADR needed)
- Task runner: `just` (Windows has no `make`)
- Packages: `pip` + `venv`, pinned in `requirements.txt`
