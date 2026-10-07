"""Object-store interface (ENGINEERING.md 11.3, 11.4).

Keys are content-addressed or versioned and never overwritten, except mutable pointers,
which change only through a compare-and-swap on their ETag (review MF-4). The local
implementation backs development and CI; the R2 implementation uses S3 conditional writes
(If-Match / If-None-Match).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

PRECONDITION_CODES = frozenset({"PreconditionFailed", "412", "ConditionalRequestConflict"})
LOCK_TIMEOUT_SECONDS = 10.0
_HIDDEN_PREFIXES = (".tmp-", ".lock-")  # in-flight writes and pointer locks


class ObjectStoreError(RuntimeError):
    pass


class PreconditionFailed(ObjectStoreError):  # noqa: N818 - the HTTP 412 name
    """A conditional write lost the race: the object changed since it was read."""


class ObjectStore(Protocol):
    def exists(self, key: str) -> bool: ...
    def get(self, key: str) -> bytes: ...
    def etag(self, key: str) -> str | None: ...
    def put_if_absent(self, key: str, data: bytes) -> bool: ...
    def put_if_match(self, key: str, data: bytes, expected_etag: str | None) -> str: ...
    def list(self, prefix: str) -> list[str]: ...


def content_etag(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_key(key: str) -> PurePosixPath:
    path = PurePosixPath(key)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise ObjectStoreError(f"unsafe object key: {key!r}")
    return path


class LocalObjectStore:
    """A directory that behaves like a bucket: atomic writes, no silent overwrites.

    Immutable objects are created with a hard link from a finished temporary file, which
    fails if the name exists, so concurrent writers cannot both win. Pointer updates hold a
    lock file while they compare and swap.
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root.joinpath(*_safe_key(key).parts)

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError as exc:
            raise ObjectStoreError(f"no such object: {key}") from exc

    def etag(self, key: str) -> str | None:
        path = self._path(key)
        return content_etag(path.read_bytes()) if path.is_file() else None

    def _stage(self, path: Path, data: bytes) -> Path:
        """Write data to a finished temporary file beside path."""
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return Path(tmp)

    def _write(self, path: Path, data: bytes) -> None:
        """Atomic replace (readers see the old or the new bytes, never a mix)."""
        tmp = self._stage(path, data)
        try:
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    def _create(self, path: Path, data: bytes) -> bool:
        """Atomically create path; False if it already exists."""
        tmp = self._stage(path, data)
        try:
            try:
                os.link(tmp, path)
            except FileExistsError:
                return False
            except OSError:
                if os.name != "nt":
                    raise
                try:  # no hard links here; Windows refuses to rename onto an existing file
                    os.rename(tmp, path)
                except FileExistsError:
                    return False
            return True
        finally:
            tmp.unlink(missing_ok=True)

    @contextmanager
    def _locked(self, path: Path) -> Iterator[None]:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = path.with_name(f".lock-{path.name}")
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise ObjectStoreError(
                        f"{lock} is held; delete it if no writer is running"
                    ) from None
                time.sleep(0.01)
        try:
            yield
        finally:
            os.close(fd)
            lock.unlink(missing_ok=True)

    def put_if_absent(self, key: str, data: bytes) -> bool:
        """Write an immutable object. Returns False if it already existed with the same
        bytes, and raises if it exists with different bytes."""
        path = self._path(key)
        if self._create(path, data):
            return True
        if path.read_bytes() != data:
            raise ObjectStoreError(f"refusing to overwrite immutable object {key}")
        return False

    def put_if_match(self, key: str, data: bytes, expected_etag: str | None) -> str:
        """Compare-and-swap for mutable pointers; expected_etag None means 'must not exist'."""
        path = self._path(key)
        if expected_etag is None:
            if not self._create(path, data):
                raise PreconditionFailed(f"{key} already exists")
            return content_etag(data)
        with self._locked(path):
            if self.etag(key) != expected_etag:
                raise PreconditionFailed(f"{key} changed since it was read")
            self._write(path, data)
        return content_etag(data)

    def list(self, prefix: str = "") -> list[str]:
        base = self.root
        if not base.exists():
            return []
        keys = [p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file()]
        return sorted(
            k
            for k in keys
            if k.startswith(prefix) and not k.rsplit("/", 1)[-1].startswith(_HIDDEN_PREFIXES)
        )


class R2ObjectStore:
    """Cloudflare R2 through its S3-compatible API, with conditional writes.

    R2 supports If-Match and If-None-Match on PutObject, which gives immutable objects
    (If-None-Match: *) and compare-and-swap pointers (If-Match: <etag>) without a lock
    server (review MF-4).
    """

    def __init__(self, bucket: str, client: object) -> None:
        self.bucket = bucket
        self._s3: Any = client

    @classmethod
    def connect(
        cls, bucket: str, account_id: str, access_key_id: str, secret_access_key: str
    ) -> R2ObjectStore:
        import boto3

        client = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name="auto",
        )
        return cls(bucket, client)

    @staticmethod
    def _code(exc: Exception) -> str:
        response = getattr(exc, "response", {}) or {}
        return str(response.get("Error", {}).get("Code", ""))

    def _head(self, key: str) -> dict[str, Any] | None:
        try:
            head: dict[str, Any] = self._s3.head_object(Bucket=self.bucket, Key=str(_safe_key(key)))
        except Exception as exc:
            if self._code(exc) in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return head

    def exists(self, key: str) -> bool:
        return self._head(key) is not None

    def get(self, key: str) -> bytes:
        try:
            body = self._s3.get_object(Bucket=self.bucket, Key=str(_safe_key(key)))["Body"]
        except Exception as exc:
            if self._code(exc) in {"404", "NoSuchKey"}:
                raise ObjectStoreError(f"no such object: {key}") from exc
            raise
        data: bytes = body.read()
        return data

    def etag(self, key: str) -> str | None:
        head = self._head(key)
        return None if head is None else str(head["ETag"]).strip('"')

    def put_if_absent(self, key: str, data: bytes) -> bool:
        """Same contract as the local store: False for identical bytes, an error otherwise."""
        try:
            self._s3.put_object(
                Bucket=self.bucket, Key=str(_safe_key(key)), Body=data, IfNoneMatch="*"
            )
        except Exception as exc:
            if self._code(exc) in PRECONDITION_CODES:
                if self.get(key) != data:
                    raise ObjectStoreError(f"refusing to overwrite immutable object {key}") from exc
                return False
            raise
        return True

    def put_if_match(self, key: str, data: bytes, expected_etag: str | None) -> str:
        condition = {"IfNoneMatch": "*"} if expected_etag is None else {"IfMatch": expected_etag}
        try:
            response = self._s3.put_object(
                Bucket=self.bucket, Key=str(_safe_key(key)), Body=data, **condition
            )
        except Exception as exc:
            if self._code(exc) in PRECONDITION_CODES:
                raise PreconditionFailed(f"{key} changed since it was read") from exc
            raise
        return str(response["ETag"]).strip('"')

    def list(self, prefix: str = "") -> list[str]:
        keys: list[str] = []
        paginator = self._s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            keys.extend(item["Key"] for item in page.get("Contents", []))
        return sorted(keys)
