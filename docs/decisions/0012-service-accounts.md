# ADR-012: Service accounts

Status: Accepted, 2026-11-12

## Context

Each source system loads data with its own account, and dbt has its own as well. They need passwords that live somewhere, and I need a way to rotate them.

## Options

Generate passwords into the git-ignored .env and rotate on demand. Rotate automatically on every policy apply. Or keep them in Windows Credential Manager through Python's keyring. Keyring is the most secure locally but awkward in CI and harder to reproduce from a clean clone. Rotating on every apply sounds strong but breaks anything still running with the old password.

## Decision

`just rotate-creds` generates a random password per service account, sets it in the database and writes it to .env. `just apply-policy` also creates passwords for any new service account that doesn't have one yet. CI will generate its own throwaway passwords each run.

One account per purpose: svc_ingest_hr, svc_ingest_crm, svc_ingest_support, svc_ingest_finance and svc_transform. If the HR key leaks, the damage is limited to inserting rows into raw.hr_employees. It can't read anything back, not even what it loaded itself.

The password gets hashed into a SCRAM verifier in Python before it's sent, so the plain text never reaches the database or its logs. That matters once pgaudit is on in Phase 4.

## Trade-offs

Passwords sit in plain text in .env on my laptop. For fake data on a free tier that's fine, but in a real setup they'd go into a secrets manager (AWS Secrets Manager, Vault) with automatic rotation. Rotation is manual for now, so it only happens when I run it.

## How I know it works

Every ingest script checks `current_user` after connecting and stops if it isn't the expected role. Rotating a role and then running ingest proves the new password works and the old one doesn't.
