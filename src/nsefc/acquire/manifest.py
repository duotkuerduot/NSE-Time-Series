"""Raw-data manifests: which files were copied or generated, from where, and their hashes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from nsefc.domain import SourceKind
from nsefc.storage import atomic_write_json, read_json, sha256_file

MANIFEST = "manifest.json"


class ManifestFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Path relative to the manifest's folder, with / separators")
    size: int
    sha256: str
    url: str | None = None
    original: str | None = Field(
        None, description="Path in the source folder or zip, with / separators"
    )
    extracted_from: str | None = None


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    source: SourceKind
    dataset_id: str | None = None
    version: int | None = None
    title: str | None = None
    licence: str | None = None
    licence_url: str | None = None
    doi: str | None = None
    citation: str | None = None
    retrieved_at: datetime | None = None
    origin: str | None = Field(None, description="Source folder or generator")
    files: list[ManifestFile] = Field(default_factory=list)

    def file_paths(self, folder: Path) -> list[Path]:
        return [folder.joinpath(*f.name.split("/")) for f in self.files]

    def content_hash(self) -> str:
        """Order-independent fingerprint of the files (used by stage fingerprints)."""
        from nsefc.storage import sha256_text

        return sha256_text(*sorted(f"{f.name}:{f.sha256}" for f in self.files))


def write_manifest(folder: Path, manifest: Manifest) -> Path:
    path = folder / MANIFEST
    atomic_write_json(path, manifest.model_dump(mode="json"))
    return path


def read_manifest(path: Path) -> Manifest:
    return Manifest.model_validate(read_json(path))


def verify(folder: Path, manifest: Manifest) -> list[str]:
    """Names of files that are missing or whose SHA-256 differs from the manifest."""
    bad = []
    for entry, path in zip(manifest.files, manifest.file_paths(folder), strict=True):
        if (
            not path.is_file()
            or path.stat().st_size != entry.size
            or sha256_file(path) != entry.sha256
        ):
            bad.append(entry.name)
    return bad


def describe_files(folder: Path, *, url_base: str | None = None) -> list[ManifestFile]:
    """Hash every regular file under ``folder`` (except the manifest itself)."""
    entries = []
    for path in sorted(p for p in folder.rglob("*") if p.is_file() and p.name != MANIFEST):
        if path.name.startswith(".tmp-"):
            continue
        relative = path.relative_to(folder).as_posix()
        entries.append(
            ManifestFile(
                name=relative,
                size=path.stat().st_size,
                sha256=sha256_file(path),
                url=f"{url_base}/{relative}" if url_base else None,
            )
        )
    return entries


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)
