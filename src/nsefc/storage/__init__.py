"""Schema, migrations, repositories and the object-store client.

Phase 0 provides the object store (local directory or Cloudflare R2). The SQLite schema,
migrations and repositories arrive in Phase 1 (ENGINEERING.md 11).
"""

from __future__ import annotations

from typing import Literal

from nsefc.config import Settings
from nsefc.storage.objectstore import (
    LocalObjectStore,
    ObjectStore,
    ObjectStoreError,
    PreconditionFailed,
    R2ObjectStore,
)

Bucket = Literal["private", "public", "scratch"]


class ReadOnlyStore:
    """Wraps a store so that every write fails: dry runs read production state only."""

    def __init__(self, inner: ObjectStore) -> None:
        self._inner = inner

    def exists(self, key: str) -> bool:
        return self._inner.exists(key)

    def get(self, key: str) -> bytes:
        return self._inner.get(key)

    def etag(self, key: str) -> str | None:
        return self._inner.etag(key)

    def list(self, prefix: str = "") -> list[str]:
        return self._inner.list(prefix)

    def put_if_absent(self, key: str, data: bytes) -> bool:
        raise ObjectStoreError(f"read-only store: refusing to write {key}")

    def put_if_match(self, key: str, data: bytes, expected_etag: str | None) -> str:
        raise ObjectStoreError(f"read-only store: refusing to write {key}")


def open_store(settings: Settings, bucket: Bucket = "private") -> ObjectStore:
    """The object store for this environment. Dry runs may write only to scratch (29.4)."""
    store = _open(settings, bucket)
    if settings.storage.read_only and bucket != "scratch":
        return ReadOnlyStore(store)
    return store


def _open(settings: Settings, bucket: Bucket) -> ObjectStore:
    if settings.storage.backend == "local":
        return LocalObjectStore(settings.storage.local_root / bucket)
    secrets = settings.secrets
    if not secrets.has_r2:
        raise ObjectStoreError("the r2 backend needs NSEFC_R2_* credentials in the environment")
    name = {
        "private": settings.storage.private_bucket,
        "public": settings.storage.public_bucket,
        "scratch": settings.storage.scratch_bucket,
    }[bucket]
    account, key_id, secret = (
        secrets.r2_account_id,
        secrets.r2_access_key_id,
        secrets.r2_secret_access_key,
    )
    if account is None or key_id is None or secret is None:  # narrowed for the type checker
        raise ObjectStoreError("incomplete R2 credentials")
    return R2ObjectStore.connect(
        name, account.get_secret_value(), key_id.get_secret_value(), secret.get_secret_value()
    )


__all__ = [
    "LocalObjectStore",
    "ObjectStore",
    "ObjectStoreError",
    "PreconditionFailed",
    "R2ObjectStore",
    "ReadOnlyStore",
    "open_store",
]
