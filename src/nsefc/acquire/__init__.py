"""Stage 1, acquire: the dataset files in ``data/source/``, ``--source-dir`` or the sample.

Nothing is downloaded: the Mendeley Data files are placed in ``data/source/`` by hand.
"""

from nsefc.acquire.manifest import (
    Manifest,
    ManifestFile,
    describe_files,
    read_manifest,
    verify,
    write_manifest,
)
from nsefc.acquire.sources import (
    AcquireError,
    AcquireResult,
    Citation,
    SourceMissingError,
    acquire_dataset,
    acquire_local,
    acquire_sample,
    load_citation,
    read_active,
    write_active,
)

__all__ = [
    "AcquireError",
    "AcquireResult",
    "Citation",
    "Manifest",
    "ManifestFile",
    "SourceMissingError",
    "acquire_dataset",
    "acquire_local",
    "acquire_sample",
    "describe_files",
    "load_citation",
    "read_active",
    "read_manifest",
    "verify",
    "write_active",
    "write_manifest",
]
