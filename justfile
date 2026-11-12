# Task runner. Install: `winget install Casey.Just`. List recipes: `just`.
set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]
set dotenv-load := false

venv_python := if os_family() == "windows" { ".venv/Scripts/python.exe" } else { ".venv/bin/python" }

default:
    @just --list

# Create the virtualenv and install pinned dependencies
setup:
    python -m venv .venv
    {{venv_python}} -m pip install --upgrade pip
    {{venv_python}} -m pip install -r requirements.txt

# Verify the warehouse is reachable (Supabase — nothing to start locally, see ADR-001)
up:
    {{venv_python}} scripts/check_connection.py

# Phase 1: generate fake data and ingest it as each service account
seed:
    @echo "Not implemented yet - Phase 1"

# Phase 2: render policy/access.yaml to SQL and apply it
apply-policy:
    @echo "Not implemented yet - Phase 2"

# Phase 3: run access tests, connecting as each real role
test:
    @echo "Not implemented yet - Phase 3"

# Phase 3: compare live database against policy/access.yaml
drift:
    @echo "Not implemented yet - Phase 3"

# Phase 4: generate the access review report
report:
    @echo "Not implemented yet - Phase 4"
