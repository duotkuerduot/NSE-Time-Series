"""Content-addressed raw archive (ENGINEERING.md 9.2 step 4, 11.3).

Every fetched file is stored before anything parses it, under
``raw/{provider}/{yyyy}/{session_date}/{sha256}.{ext}`` with a ``.meta.json`` sidecar.
The same bytes fetched twice are stored once.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime

from nsefc.storage.objectstore import ObjectStore

EXTENSIONS = {"application/pdf": "pdf", "text/html": "html", "text/csv": "csv"}


@dataclass(frozen=True, slots=True)
class RawArtifact:
    provider_id: str
    session_date: date
    url: str
    fetched_at: datetime
    content: bytes
    content_type: str
    status_code: int
    etag: str | None = None
    last_modified: str | None = None

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    @property
    def extension(self) -> str:
        if self.content.startswith(b"%PDF"):
            return "pdf"
        return EXTENSIONS.get(self.content_type.split(";")[0].strip().lower(), "bin")


def raw_key(artifact: RawArtifact) -> str:
    day = artifact.session_date
    return (
        f"raw/{artifact.provider_id}/{day.year:04d}/{day.isoformat()}/"
        f"{artifact.sha256}.{artifact.extension}"
    )


def archive(store: ObjectStore, artifact: RawArtifact) -> tuple[str, bool]:
    """Store the bytes and their metadata. Returns (key, newly_written)."""
    key = raw_key(artifact)
    written = store.put_if_absent(key, artifact.content)
    meta = {k: v for k, v in asdict(artifact).items() if k != "content"}
    meta.update(
        session_date=artifact.session_date.isoformat(),
        fetched_at=artifact.fetched_at.isoformat(),
        sha256=artifact.sha256,
        size=len(artifact.content),
    )
    meta_key = key.rsplit(".", 1)[0] + ".meta.json"
    if not store.exists(meta_key):
        store.put_if_absent(meta_key, (json.dumps(meta, indent=2, sort_keys=True) + "\n").encode())
    return key, written
