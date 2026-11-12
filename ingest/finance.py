"""Loads the finance export as svc_ingest_finance."""
from ingest.base import ingest

if __name__ == "__main__":
    ingest("finance")
