"""Thin entry point for daily ingestion (ENGINEERING.md 9.2), equivalent to `nsefc ingest fetch`.

The ingestion service arrives in Phase 2; until then this exits with a pointer to the spike.
"""

from nsefc.cli import app

if __name__ == "__main__":
    app(["ingest", "fetch"])
