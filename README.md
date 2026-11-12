# SystemArch: a governed data warehouse

A small Postgres warehouse where access control is the point. Four fake source systems load into one warehouse, and every person and service account gets only the access it needs. That access is enforced in the database itself (grants, column masking, row-level security) and generated from a single policy file. Tests, drift detection and an access review report then prove who can see what.

Where I am: Phase 2 is done. Ten fake people from an IdP export log in through group roles, personal data is hashed in `marts` with a clear-text `marts_restricted` behind clearance levels, and sales only sees its own region through RLS. Next up is Phase 3: automated access tests, drift detection and CI.

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

`policy/access.yaml` is the single source of truth for access, and `policy/people.yaml` stands in for the identity provider. `generator/` turns them into SQL, and `ddl/governance.sql` holds the functions that re-apply access every time dbt rebuilds a table. `ddl/` holds the raw table definitions, `seed/` the fake data generators, `ingest/` one loader per source, and `dbt/` the staging and mart models.

The reasoning behind each choice is in [docs/decisions](docs/decisions/README.md).

## How changes get in

`main` is protected. Every change goes through a pull request, review comments have to be resolved before it can merge, and PRs are squash-merged so history stays one commit per change. Force pushes and deleting `main` are blocked for everyone, me included. Secret scanning with push protection, Dependabot alerts and private vulnerability reporting are on.
