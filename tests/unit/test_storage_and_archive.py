from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from nsefc.ingestion.archive import RawArtifact, archive, raw_key
from nsefc.storage.objectstore import LocalObjectStore, ObjectStoreError, PreconditionFailed


def test_put_if_absent_is_idempotent_and_immutable(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    assert store.put_if_absent("a/b.txt", b"one")
    assert not store.put_if_absent("a/b.txt", b"one")
    with pytest.raises(ObjectStoreError, match="overwrite"):
        store.put_if_absent("a/b.txt", b"two")
    assert store.list("a/") == ["a/b.txt"]


def test_unsafe_keys_rejected(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    for key in ("../escape", "/abs", ""):
        with pytest.raises(ObjectStoreError):
            store.put_if_absent(key, b"x")


def test_pointer_compare_and_swap(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    first = store.put_if_match("db/current.json", b'{"v":1}', expected_etag=None)
    with pytest.raises(PreconditionFailed):
        store.put_if_match("db/current.json", b'{"v":2}', expected_etag=None)
    second = store.put_if_match("db/current.json", b'{"v":2}', expected_etag=first)
    with pytest.raises(PreconditionFailed):  # a writer that read version 1 loses
        store.put_if_match("db/current.json", b'{"v":3}', expected_etag=first)
    assert store.etag("db/current.json") == second


def test_archive_is_content_addressed(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    artifact = RawArtifact(
        "kingdom",
        date(2026, 10, 7),
        "https://example.test/x.pdf",
        datetime(2026, 10, 7, 17, 8, tzinfo=UTC),
        b"%PDF-1.7 body",
        "application/pdf",
        200,
    )
    key, written = archive(store, artifact)
    assert written and key == raw_key(artifact)
    assert key.startswith("raw/kingdom/2026/2026-10-07/") and key.endswith(".pdf")
    _, again = archive(store, artifact)
    assert not again
    meta = json.loads(store.get(key.replace(".pdf", ".meta.json")))
    assert meta["sha256"] == artifact.sha256 and meta["size"] == len(artifact.content)
