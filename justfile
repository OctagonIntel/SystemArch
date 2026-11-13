# Task runner. Install with `winget install Casey.Just`, then run `just` to see the recipes.
set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]
set dotenv-load := true

py  := if os_family() == "windows" { ".venv/Scripts/python.exe" } else { ".venv/bin/python" }
dbt := if os_family() == "windows" { ".venv/Scripts/dbt.exe" } else { ".venv/bin/dbt" }

default:
    @just --list

# Create the virtualenv and install pinned dependencies
setup:
    python -m venv .venv
    {{py}} -m pip install --upgrade pip
    {{py}} -m pip install -r requirements.txt

# Check the warehouse is reachable
up:
    {{py}} -m scripts.check_connection

# Show the SQL the policy turns into, without running it
plan:
    {{py}} -m generator.apply --plan

# Apply policy/access.yaml to the warehouse
apply-policy:
    {{py}} -m generator.apply

# New passwords for service accounts (all of them, or the ones you name)
rotate-creds *roles:
    {{py}} -m scripts.rotate_creds {{roles}}

# Write fake source exports to data/exports
generate:
    {{py}} -m seed.generate

# Load every source into raw, each as its own service account
ingest:
    {{py}} -m ingest.hr
    {{py}} -m ingest.crm
    {{py}} -m ingest.support
    {{py}} -m ingest.finance

# Build staging and marts with dbt, as svc_transform
transform:
    {{dbt}} build --project-dir dbt --profiles-dir dbt

# Everything from an empty warehouse to built marts
seed: apply-policy generate ingest
    @just transform  # a fresh `just` so it picks up passwords apply-policy just wrote to .env

# Access tests, separation of duties and drift, logged in as each real person
test *args:
    {{py}} -m pytest {{args}}

# List every difference between the live database and the policy
drift:
    {{py}} -m drift.check

# Phase 4: access review report
report:
    @echo "Not built yet, Phase 4"
