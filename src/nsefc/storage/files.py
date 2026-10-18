"""Plain file helpers: hashing, atomic writes and atomic folder swaps.

Every stage writes its outputs somewhere temporary and then moves them into place, so a
crash or Ctrl+C never leaves a half-written file where a later stage (or the local server)
would read it. Works the same on Windows, macOS and Linux.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator
from pathlib import Path, PurePosixPath
from typing import Any

CHUNK = 1 << 20


class UnsafePathError(ValueError):
    """A requested path would leave its root folder."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def canonical_json(value: Any) -> str:
    """Stable JSON for hashing and for byte-identical repeat runs."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pretty_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=False, ensure_ascii=False) + "\n"


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Short temporary names: Windows paths are limited to 260 characters.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _replace(Path(tmp), path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, value: Any, *, pretty: bool = True) -> None:
    atomic_write_text(path, pretty_json(value) if pretty else canonical_json(value) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _replace(source: Path, target: Path, attempts: int = 5) -> None:
    # os.replace is atomic on one volume. Windows can refuse briefly while another process
    # (an antivirus scanner, the local server) holds the target open, so retry a few times.
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.2 * (attempt + 1))


def remove_tree(path: Path) -> None:
    """Delete a folder, clearing read-only flags that Windows sets on some files."""

    def _retry_readonly(func: Any, target: str, _exc: Any) -> None:
        os.chmod(target, 0o700)
        func(target)

    if not Path(path).exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_retry_readonly)
    else:  # pragma: no cover - Python 3.11
        shutil.rmtree(path, onerror=_retry_readonly)


def swap_dir(staged: Path, final: Path) -> None:
    """Move a finished folder into place, replacing any previous one.

    Directories cannot be replaced atomically on every platform, so the old folder is first
    renamed aside; a reader sees either the old complete folder or the new complete folder.
    """
    staged, final = Path(staged), Path(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    backup = final.with_name(f".old-{final.name}-{uuid.uuid4().hex[:8]}")
    had_old = final.exists()
    if had_old:
        _replace(final, backup)
    try:
        _replace(staged, final)
    except BaseException:
        if had_old and not final.exists():
            _replace(backup, final)
        raise
    if had_old:
        remove_tree(backup)


@contextlib.contextmanager
def staged_dir(final: Path) -> Iterator[Path]:
    """Yield an empty folder beside ``final``; on success swap it into place."""
    final = Path(final)
    final.parent.mkdir(parents=True, exist_ok=True)
    staged = final.with_name(f".tmp-{final.name}-{uuid.uuid4().hex[:8]}")
    staged.mkdir()
    try:
        yield staged
    except BaseException:
        remove_tree(staged)
        raise
    swap_dir(staged, final)


def sweep_temporaries(root: Path) -> int:
    """Remove .tmp-* and .old-* leftovers anywhere under ``root`` (an interrupted run)."""
    root = Path(root)
    if not root.is_dir():
        return 0
    folders = [root, *(p for p in root.rglob("*") if p.is_dir())]
    return sum(clean_stale_temporaries(folder) for folder in folders)


def clean_stale_temporaries(folder: Path) -> int:
    """Remove .tmp-* and .old-* leftovers from an interrupted run."""
    removed = 0
    if not Path(folder).is_dir():
        return 0
    for child in Path(folder).iterdir():
        if child.name.startswith((".tmp-", ".old-")):
            if child.is_dir():
                remove_tree(child)
            else:
                child.unlink(missing_ok=True)
            removed += 1
    return removed


def safe_join(root: Path, relative: str) -> Path:
    """``root / relative``, refusing anything that resolves outside root."""
    posix = PurePosixPath(relative.replace("\\", "/"))
    if posix.is_absolute() or ".." in posix.parts:
        raise UnsafePathError(relative)
    root_resolved = Path(root).resolve()
    candidate = (root_resolved / Path(*posix.parts)).resolve() if posix.parts else root_resolved
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise UnsafePathError(relative)
    return candidate


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".tmp-")
    os.close(fd)
    try:
        shutil.copyfile(source, tmp)
        _replace(Path(tmp), target)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
