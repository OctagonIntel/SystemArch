# SystemArch: a governed data warehouse

A small Postgres warehouse where access control is the point. Four fake source systems load into one warehouse, and every person and service account gets only the access it needs. That access is enforced in the database itself (grants, column masking, row-level security) and generated from a single policy file. Tests, drift detection and an access review report then prove who can see what.

Where I am: Phase 1 is done. The data generators, ingestion and dbt models work, and the service accounts are already driven by the policy file. Next up is Phase 2: human roles, masking and RLS.

```mermaid
flowchart LR
  subgraph Sources[Fake source systems]
    HR[HR system]
    CRM[CRM]
    SUP[Support tickets]
    FIN[Finance]
  end

  subgraph WH[Postgres warehouse]
    RAW[(raw)]
    STG[(staging)]
    MART[(marts)]
    AUD[(audit)]
  end

  HR -->|svc_ingest_hr| RAW
  CRM -->|svc_ingest_crm| RAW
  SUP -->|svc_ingest_support| RAW
  FIN -->|svc_ingest_finance| RAW
  RAW -->|svc_transform dbt| STG --> MART

  POL[policy/access.yaml] --> GEN[generator] -->|GRANTs + RLS + masking| WH
  MART --> Analyst & HRrole[HR] & Finance & Sales[Regional sales] & Support
  AUD --> Auditor
  WH --> DRIFT[drift check] & TESTS[access tests] & REPORT[access review report]
```

## Running it

You need Python 3.11+, [just](https://github.com/casey/just) and a Postgres to point at. I use a Supabase free project, see [ADR-001](docs/decisions/0001-where-the-warehouse-runs.md).

```
copy .env.example .env    # fill in the connection details
just setup                # virtualenv and dependencies
just up                   # check the connection
just seed                 # apply policy, generate data, ingest, build marts
```

`just plan` shows the SQL the policy turns into without running it. Run `just` on its own to see every command.

## Layout

`policy/access.yaml` is the single source of truth for access. `generator/` turns it into SQL. `ddl/` holds the raw table definitions, `seed/` the fake data generators, `ingest/` one loader per source, and `dbt/` the staging and mart models.

The reasoning behind each choice is in [docs/decisions](docs/decisions/README.md).
