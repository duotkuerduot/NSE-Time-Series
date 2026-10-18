"""Stage 1, acquire: where the raw files come from. Nothing is downloaded.

* default: ``data/source/``, where the Mendeley Data price files are placed by hand, cited as
  recorded in ``reference/mendeley.yaml``;
* ``--source-dir PATH``: any folder of files in the same format;
* ``--sample``: the deterministic synthetic dataset.

The chosen files are copied once into ``data/raw/`` with a manifest of SHA-256 hashes, so
every canonical row traces to an exact file and later edits to the source folder are noticed:
a changed file gets a new manifest and the next ingest re-runs.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal

import yaml

from nsefc.acquire.manifest import (
    MANIFEST,
    Manifest,
    ManifestFile,
    describe_files,
    read_manifest,
    utc_now,
    verify,
    write_manifest,
)
from nsefc.calendar import TradingCalendar
from nsefc.domain import SourceKind
from nsefc.sample import GENERATOR_VERSION, generate
from nsefc.storage import (
    atomic_write_bytes,
    atomic_write_json,
    copy_file,
    read_json,
    sha256_bytes,
    sha256_file,
    sha256_text,
    staged_dir,
)

Mode = Literal["dataset", "local", "sample"]
ACTIVE = "active.json"
COPIED_SUFFIXES = {".csv", ".zip"}
TEXT_SUFFIXES = {".csv"}


class AcquireError(RuntimeError):
    """The dataset could not be read (exit code 10)."""


class SourceMissingError(AcquireError):
    """The source folder does not exist or holds no dataset files."""


@dataclass(frozen=True, slots=True)
class Citation:
    """The dataset's identity and attribution, from reference/mendeley.yaml."""

    dataset_id: str
    version: int
    title: str
    authors: tuple[str, ...]
    year: int
    publisher: str
    doi: str | None
    url: str | None
    licence: str | None
    licence_url: str | None
    text: str


def load_citation(path: Path) -> Citation:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        dataset = data["dataset"]
        return Citation(
            dataset_id=str(dataset["id"]),
            version=int(dataset["version"]),
            title=str(dataset["title"]),
            authors=tuple(str(a) for a in dataset.get("authors") or []),
            year=int(dataset["year"]),
            publisher=str(dataset.get("publisher", "Mendeley Data")),
            doi=dataset.get("doi"),
            url=dataset.get("url"),
            licence=dataset.get("licence") or None,
            licence_url=dataset.get("licence_url") or None,
            text=" ".join(str(data["citation"]).split()),
        )
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        raise AcquireError(f"cannot read the dataset citation in {path}: {exc}") from exc


@dataclass(slots=True)
class AcquireResult:
    mode: Mode
    manifests: list[Path]
    copied: bool = False
    notes: list[str] = field(default_factory=list)

    def manifest_objects(self) -> list[Manifest]:
        return [read_manifest(p) for p in self.manifests]


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def content_sha256(path: Path) -> str:
    """The SHA-256 that identifies a source file, as its copy will have it.

    CSV text is hashed with Windows line endings read as LF. Downloaded copies can have CRLF
    line endings while other copies of the same files have LF; without this one file would
    hash differently from one machine to the next, and corrections keyed by hash would
    silently not apply.
    """
    if path.suffix.lower() in TEXT_SUFFIXES:
        return sha256_bytes(_lf(path.read_bytes()))
    return sha256_file(path)


def _copy_source(path: Path, target: Path) -> None:
    """Copy one source file; CSV text is written with LF line endings (see content_sha256)."""
    if path.suffix.lower() in TEXT_SUFFIXES:
        atomic_write_bytes(target, _lf(path.read_bytes()))
    else:
        copy_file(path, target)


def _unsafe(member_name: str) -> bool:
    """A zip member that would land outside its folder, on any operating system."""
    posix = PurePosixPath(member_name.replace("\\", "/"))
    return posix.is_absolute() or ".." in posix.parts or bool(PureWindowsPath(member_name).drive)


def _flat_name(relative: str, taken: set[str]) -> str:
    """The file's own name, made unique with a short hash if another file already has it.

    Raw copies sit directly in their folder: the source's nested folder names are long, and a
    Windows path longer than 260 characters cannot be created.
    """
    base = PurePosixPath(relative).name
    name = base if base not in taken else f"{sha256_text(relative)[:8]}-{base}"
    taken.add(name)
    return name


def extract_zip(path: Path, folder: Path, taken: set[str] | None = None) -> list[ManifestFile]:
    """Extract a zip's files into ``folder``, refusing members that would escape it."""
    taken = set() if taken is None else taken
    entries = []
    try:
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir() or _unsafe(member.filename):
                    continue
                inner = member.filename.replace("\\", "/")
                target = folder / _flat_name(inner, taken)
                with archive.open(member) as source:
                    if PurePosixPath(inner).suffix.lower() in TEXT_SUFFIXES:
                        target.write_bytes(_lf(source.read()))
                    else:
                        with target.open("wb") as sink:
                            while chunk := source.read(1 << 20):
                                sink.write(chunk)
                entries.append(
                    ManifestFile(
                        name=target.name,
                        size=target.stat().st_size,
                        sha256=sha256_file(target),
                        original=f"{path.name}/{inner}",
                        extracted_from=path.name,
                    )
                )
    except zipfile.BadZipFile as exc:
        raise AcquireError(f"{path.name} is not a valid zip file") from exc
    return entries


def _source_files(source_dir: Path) -> list[Path]:
    """The .csv and .zip files under ``source_dir``; anything else (a README) is ignored."""
    if not source_dir.is_dir():
        raise SourceMissingError(f"{source_dir} is not a folder")
    files = sorted(
        p
        for p in source_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in COPIED_SUFFIXES and not p.name.startswith(".")
    )
    if not files:
        raise SourceMissingError(f"no .csv or .zip files in {source_dir}")
    return files


def _copy_folder(
    raw_root: Path, source_dir: Path, destination: Path | None, manifest_fields: dict[str, object]
) -> AcquireResult:
    files = _source_files(source_dir)
    hashes = [(p.relative_to(source_dir).as_posix(), content_sha256(p)) for p in files]
    key = sha256_text(*(f"{n}:{h}" for n, h in hashes))[:16]
    folder = destination or raw_root / "local" / key
    mode: Mode = "dataset" if destination else "local"
    manifest_path = folder / MANIFEST
    if manifest_path.is_file():
        existing = read_manifest(manifest_path)
        # The same files, no more and no fewer: a file removed from the source folder must not
        # linger in the copy (files extracted from zips are not in the source listing).
        same_files = set(hashes) == {
            (f.original or f.name, f.sha256) for f in existing.files if not f.extracted_from
        }
        if same_files and not verify(folder, existing):
            if any(getattr(existing, k) != v for k, v in manifest_fields.items()):
                # The citation or licence was edited: refresh the record, keep the copies.
                write_manifest(folder, existing.model_copy(update=manifest_fields))
            return AcquireResult(mode, [manifest_path])
    with staged_dir(folder) as staged:
        taken: set[str] = set()
        entries = []
        for path, (relative, _digest) in zip(files, hashes, strict=True):
            target = staged / _flat_name(relative, taken)
            _copy_source(path, target)
            entries.append(
                ManifestFile(
                    name=target.name,
                    size=target.stat().st_size,
                    sha256=sha256_file(target),
                    original=relative,
                )
            )
            if target.suffix.lower() == ".zip":
                entries += extract_zip(target, staged, taken)
        manifest = Manifest(retrieved_at=utc_now(), files=entries, **manifest_fields)
        write_manifest(staged, manifest)
    return AcquireResult(mode, [manifest_path], copied=True)


def acquire_dataset(
    raw_root: Path, source_dir: Path, citation: Citation, *, origin: str | None = None
) -> AcquireResult:
    """The default: the Mendeley files in ``source_dir``, recorded with their citation.

    ``origin`` is how the manifest names the folder (``data/source``, say); it defaults to the
    folder's path.
    """
    destination = raw_root / "mendeley" / citation.dataset_id / f"v{citation.version}"
    fields: dict[str, object] = {
        "source": SourceKind.MENDELEY,
        "dataset_id": citation.dataset_id,
        "version": citation.version,
        "title": citation.title,
        "licence": citation.licence,
        "licence_url": citation.licence_url,
        "doi": citation.doi,
        "citation": citation.text,
        "origin": origin or source_dir.as_posix(),
    }
    return _copy_folder(raw_root, source_dir, destination, fields)


def acquire_local(raw_root: Path, source_dir: Path) -> AcquireResult:
    """``--source-dir``: any folder of files in the dataset's format."""
    source_dir = Path(source_dir).expanduser()
    fields: dict[str, object] = {
        "source": SourceKind.LOCAL,
        "title": f"Local files from {source_dir.name}",
        "origin": str(source_dir),
    }
    return _copy_folder(raw_root, source_dir, None, fields)


def acquire_sample(raw_root: Path, calendar: TradingCalendar) -> AcquireResult:
    """``--sample``: generate the synthetic dataset once per generator version."""
    folder = raw_root / "sample" / f"v{GENERATOR_VERSION}"
    if (folder / MANIFEST).is_file() and not verify(folder, read_manifest(folder / MANIFEST)):
        return AcquireResult("sample", [folder / MANIFEST])
    with staged_dir(folder) as staged:
        generate(staged, calendar)
        manifest = Manifest(
            source=SourceKind.SAMPLE,
            version=GENERATOR_VERSION,
            title="Synthetic sample dataset (fictional tickers, not market data)",
            licence="Generated by nsefc; no restrictions",
            citation="nsefc synthetic sample dataset",
            retrieved_at=None,  # deterministic manifest: the same bytes on every machine
            origin="nsefc.sample",
            files=describe_files(staged),
        )
        write_manifest(staged, manifest)
    return AcquireResult("sample", [folder / MANIFEST], copied=True)


def write_active(raw_root: Path, result: AcquireResult) -> Path:
    """Record which manifests the next ingest reads (no timestamps: stays byte-stable)."""
    path = raw_root / ACTIVE
    atomic_write_json(
        path,
        {
            "mode": result.mode,
            "manifests": [p.relative_to(raw_root).as_posix() for p in result.manifests],
        },
    )
    return path


def read_active(raw_root: Path) -> AcquireResult:
    path = raw_root / ACTIVE
    if not path.is_file():
        raise AcquireError("no acquired data yet: run `nsefc acquire` (or `nsefc run`) first")
    data = read_json(path)
    manifests = [raw_root.joinpath(*m.split("/")) for m in data["manifests"]]
    missing = [m for m in manifests if not m.is_file()]
    if missing:
        raise AcquireError(f"acquired data is incomplete; missing {missing[0]}")
    return AcquireResult(data["mode"], manifests)
