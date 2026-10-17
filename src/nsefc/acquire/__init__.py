"""Stage 1, acquire (§5): the repository's dataset folder, ``--source-dir`` or the sample.

Nothing is downloaded (owner decision D-10): the Mendeley Data files ship in ``NSE Data/``.
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
