# What I'd do differently at scale

Notes I'm collecting as I go, for the "what next" part of the presentation.

**Ingestion with dlt.** I wrote plain Python ingest scripts because dlt wants to create and alter its own tables, which means the ingest accounts would need CREATE rights and would end up owning tables. That clashes with keeping them insert-only. At scale I'd still use dlt (or similar) for schema evolution and incremental loads, but have it load into a landing schema per source that the source account owns, and treat that schema as untrusted until the transform layer copies it into raw.

**Secrets.** Service account passwords live in a local .env right now. In a real setup they'd go into a secrets manager with automatic rotation, or better, be replaced by short-lived credentials like IAM database auth.

**Raw retention.** Raw is append-only and keeps every load. I'd partition it by load date and drop old partitions after a retention period.
