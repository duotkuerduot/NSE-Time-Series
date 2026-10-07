from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from nsefc.config import load_settings
from nsefc.storage import (
    LocalObjectStore,
    ObjectStoreError,
    PreconditionFailed,
    R2ObjectStore,
    ReadOnlyStore,
    open_store,
)


@pytest.fixture
def r2() -> Iterator[R2ObjectStore]:
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket="nsefc-data")
        yield R2ObjectStore("nsefc-data", client)


def test_r2_immutable_put(r2: R2ObjectStore) -> None:
    assert r2.put_if_absent("raw/a.pdf", b"%PDF one")
    assert not r2.put_if_absent("raw/a.pdf", b"%PDF one")
    assert r2.get("raw/a.pdf") == b"%PDF one"
    assert r2.exists("raw/a.pdf") and not r2.exists("raw/b.pdf")
    assert r2.list("raw/") == ["raw/a.pdf"]


def test_r2_pointer_compare_and_swap(r2: R2ObjectStore) -> None:
    first = r2.put_if_match("db/current.json", b"v1", expected_etag=None)
    assert r2.etag("db/current.json") == first
    second = r2.put_if_match("db/current.json", b"v2", expected_etag=first)
    with pytest.raises(PreconditionFailed):
        r2.put_if_match("db/current.json", b"v3", expected_etag=first)
    assert r2.etag("db/current.json") == second


def test_r2_missing_object(r2: R2ObjectStore) -> None:
    with pytest.raises(ObjectStoreError):
        r2.get("nope")
    assert r2.etag("nope") is None


def test_open_store_local_and_read_only(repo_root: Path, tmp_path: Path) -> None:
    dev = load_settings(
        "development",
        config_dir=repo_root / "config",
        environ={},
        overrides={"storage.local_root": str(tmp_path)},
    )
    store = open_store(dev, "private")
    assert isinstance(store, LocalObjectStore)
    assert store.put_if_absent("x.txt", b"x")
    assert (tmp_path / "private" / "x.txt").exists()

    dryrun = load_settings(
        "dryrun",
        config_dir=repo_root / "config",
        environ={},
        overrides={"storage.backend": "local", "storage.local_root": str(tmp_path)},
    )
    readonly = open_store(dryrun, "private")
    assert isinstance(readonly, ReadOnlyStore)
    assert readonly.get("x.txt") == b"x"
    with pytest.raises(ObjectStoreError, match="read-only"):
        readonly.put_if_absent("y.txt", b"y")
    assert isinstance(open_store(dryrun, "scratch"), LocalObjectStore)


def test_r2_backend_needs_credentials(repo_root: Path) -> None:
    production = load_settings("production", config_dir=repo_root / "config", environ={})
    with pytest.raises(ObjectStoreError, match="credentials"):
        open_store(production, "private")


def test_r2_refuses_to_overwrite_with_different_bytes(r2: R2ObjectStore) -> None:
    assert r2.put_if_absent("raw/a.pdf", b"%PDF one")
    with pytest.raises(ObjectStoreError, match="refusing to overwrite"):
        r2.put_if_absent("raw/a.pdf", b"%PDF two")
    assert r2.get("raw/a.pdf") == b"%PDF one"


class RacingStore(LocalObjectStore):
    """Another writer creates the object after this one has staged its bytes."""

    def _stage(self, path: Path, data: bytes) -> Path:
        staged = super()._stage(path, data)
        if not path.exists():
            path.write_bytes(b"the other writer")
        return staged


def test_local_put_if_absent_never_overwrites_a_racing_writer(tmp_path: Path) -> None:
    store = RacingStore(tmp_path)
    with pytest.raises(ObjectStoreError, match="refusing to overwrite"):
        store.put_if_absent("raw/a.pdf", b"mine")
    assert (tmp_path / "raw" / "a.pdf").read_bytes() == b"the other writer"
    assert store.list() == ["raw/a.pdf"]  # no temporary files left behind


class SlowSwapStore(LocalObjectStore):
    def __init__(self, root: Path, inside: threading.Event) -> None:
        super().__init__(root)
        self.inside = inside

    def _write(self, path: Path, data: bytes) -> None:
        self.inside.set()
        time.sleep(0.2)  # hold the pointer lock while a second writer arrives
        super()._write(path, data)


def test_local_compare_and_swap_admits_one_writer(tmp_path: Path) -> None:
    first = LocalObjectStore(tmp_path).put_if_match("db/current.json", b"v1", None)
    inside = threading.Event()
    slow = SlowSwapStore(tmp_path, inside)
    results: dict[str, object] = {}

    def swap(name: str, store: LocalObjectStore, data: bytes) -> None:
        try:
            results[name] = store.put_if_match("db/current.json", data, first)
        except PreconditionFailed as exc:
            results[name] = exc

    a = threading.Thread(target=swap, args=("a", slow, b"v2-a"))
    a.start()
    assert inside.wait(5)
    swap("b", LocalObjectStore(tmp_path), b"v2-b")  # same expected ETag, while a holds the lock
    a.join()
    assert results["a"] == LocalObjectStore(tmp_path).etag("db/current.json")
    assert isinstance(results["b"], PreconditionFailed)
    assert (tmp_path / "db" / "current.json").read_bytes() == b"v2-a"


def test_local_pointer_creation_is_exclusive(tmp_path: Path) -> None:
    store = LocalObjectStore(tmp_path)
    store.put_if_match("db/current.json", b"v1", None)
    with pytest.raises(PreconditionFailed):
        store.put_if_match("db/current.json", b"v1 again", None)
