"""Stage 2, ingest (§6): reader, corrections, aliases, panel rules and quality checks."""

from nsefc.ingest.corrections import CorrectionError, load_corrections
from nsefc.ingest.reader import SchemaError
from nsefc.ingest.stage import IngestResult, SourceFiles, ingest, read_import_file

__all__ = [
    "CorrectionError",
    "IngestResult",
    "SchemaError",
    "SourceFiles",
    "ingest",
    "load_corrections",
    "read_import_file",
]
