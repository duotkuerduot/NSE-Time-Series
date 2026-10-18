"""Acquire: copy, hash, cache, and refuse unsafe or missing input."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from nsefc.acquire import (
    AcquireError,
    acquire_dataset,
    acquire_local,
    acquire_sample,
    load_citation,
    read_active,
    read_manifest,
    write_active,
)
from nsefc.acquire.sources import content_sha256, extract_zip
from nsefc.calendar import TradingCalendar
from nsefc.domain import SourceKind
from nsefc.ingest.corrections import load_corrections
from nsefc.pipeline.context import RunContext, StageError
from nsefc.pipeline.stages import stage_acquire
from nsefc.sample import generate
from nsefc.storage import sha256_bytes, sha256_file
from tests.conftest import settings_for

CITATION = (
    'Wanjawa, Barack (2026), "Kenya Nairobi Securities Exchange (NSE) All Stocks Prices 2026", '
    "Mendeley Data, V1, doi: 10.17632/hvmhnp7f9r.1"
)


def make_folder(root: Path) -> Path:
    folder = root / "source" / "part"
    folder.mkdir(parents=True)
    (folder / "NSE_data_all_stocks_2099.csv").write_text(
        "Date,Code\n2-Jan-99,AAA\n", encoding="utf-8"
    )
    (folder / "notes.txt").write_text("ignored", encoding="utf-8")
    return root / "source"


def test_the_citation_names_the_2026_collection(repo_root: Path) -> None:
    citation = load_citation(repo_root / "reference" / "mendeley.yaml")
    assert citation.text == CITATION
    assert citation.doi == "10.17632/hvmhnp7f9r.1"
    assert (citation.dataset_id, citation.version) == ("hvmhnp7f9r", 1)
    assert citation.licence is None  # empty until confirmed from the dataset page


def test_dataset_copy_records_hashes_and_citation(tmp_path: Path, repo_root: Path) -> None:
    source = make_folder(tmp_path)
    citation = load_citation(repo_root / "reference" / "mendeley.yaml")
    result = acquire_dataset(tmp_path / "raw", source, citation, origin="data/source")
    assert result.copied and result.mode == "dataset"
    (manifest_path,) = result.manifests
    assert manifest_path == tmp_path / "raw" / "mendeley" / "hvmhnp7f9r" / "v1" / "manifest.json"
    manifest = read_manifest(manifest_path)
    assert manifest.source is SourceKind.MENDELEY
    assert manifest.citation == CITATION
    assert manifest.origin == "data/source"
    # Copies sit flat in their folder (short Windows paths); the manifest keeps the original.
    assert [(f.name, f.original) for f in manifest.files] == [
        ("NSE_data_all_stocks_2099.csv", "part/NSE_data_all_stocks_2099.csv")
    ]
    copied = manifest_path.parent / "NSE_data_all_stocks_2099.csv"
    assert manifest.files[0].sha256 == sha256_file(copied)


def test_second_acquire_is_cached_until_a_file_changes(tmp_path: Path, repo_root: Path) -> None:
    source = make_folder(tmp_path)
    citation = load_citation(repo_root / "reference" / "mendeley.yaml")
    raw = tmp_path / "raw"
    assert acquire_dataset(raw, source, citation).copied
    assert not acquire_dataset(raw, source, citation).copied
    # Changed, added and removed files all produce a new copy.
    (source / "part" / "NSE_data_all_stocks_2099.csv").write_text(
        "Date,Code\n3-Jan-99,AAA\n", encoding="utf-8"
    )
    assert acquire_dataset(raw, source, citation).copied
    (source / "part" / "NSE_data_all_stocks_2098.csv").write_text("Date,Code\n", encoding="utf-8")
    assert acquire_dataset(raw, source, citation).copied
    (source / "part" / "NSE_data_all_stocks_2098.csv").unlink()
    result = acquire_dataset(raw, source, citation)
    assert result.copied
    assert [f.name for f in read_manifest(result.manifests[0]).files] == [
        "NSE_data_all_stocks_2099.csv"
    ]


def test_a_tampered_copy_is_replaced(tmp_path: Path, repo_root: Path) -> None:
    source = make_folder(tmp_path)
    citation = load_citation(repo_root / "reference" / "mendeley.yaml")
    raw = tmp_path / "raw"
    result = acquire_dataset(raw, source, citation)
    copied = result.manifests[0].parent / "NSE_data_all_stocks_2099.csv"
    copied.write_text("tampered", encoding="utf-8")
    assert acquire_dataset(raw, source, citation).copied
    assert copied.read_text(encoding="utf-8").startswith("Date,Code")


def test_local_folder_and_zip_extraction(tmp_path: Path) -> None:
    source = tmp_path / "elsewhere"
    source.mkdir()
    with zipfile.ZipFile(source / "data.zip", "w") as archive:
        archive.writestr("inner/NSE_data_all_stocks_2099.csv", "Date,Code\n")
    result = acquire_local(tmp_path / "raw", source)
    manifest = read_manifest(result.manifests[0])
    assert manifest.source is SourceKind.LOCAL
    names = {f.name: f.extracted_from for f in manifest.files}
    assert names == {"data.zip": None, "NSE_data_all_stocks_2099.csv": "data.zip"}
    assert not acquire_local(tmp_path / "raw", source).copied  # zip sources are cached too


def test_zip_members_cannot_escape(tmp_path: Path) -> None:
    path = tmp_path / "evil.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../outside.csv", "x")
        archive.writestr("..\\windows.csv", "x")
        archive.writestr("C:/drive.csv", "x")
        archive.writestr("ok/inside.csv", "y")
    target = tmp_path / "out"
    target.mkdir()
    entries = extract_zip(path, target)
    assert [(e.name, e.original) for e in entries] == [("inside.csv", "evil.zip/ok/inside.csv")]
    assert sorted(p.name for p in target.iterdir()) == ["inside.csv"]


def test_missing_or_empty_folders_are_refused(tmp_path: Path) -> None:
    with pytest.raises(AcquireError, match="not a folder"):
        acquire_local(tmp_path / "raw", tmp_path / "nope")
    (tmp_path / "empty").mkdir()
    with pytest.raises(AcquireError, match=r"no \.csv or \.zip"):
        acquire_local(tmp_path / "raw", tmp_path / "empty")


def test_stage_acquire_exits_10_with_guidance(tmp_path: Path) -> None:
    ctx = RunContext(settings=settings_for(tmp_path / "data"), echo=lambda _m: None)
    with pytest.raises(StageError) as raised:
        stage_acquire(ctx, source_dir=tmp_path / "nope")
    assert raised.value.exit_code == 10
    assert "--source-dir" in str(raised.value) and "--sample" in str(raised.value)


def test_without_the_dataset_acquire_says_where_it_goes(tmp_path: Path) -> None:
    """A fresh clone has no dataset files: the message says how to get them."""
    ctx = RunContext(settings=settings_for(tmp_path / "data"), echo=lambda _m: None)
    (tmp_path / "data" / "source").mkdir(parents=True)
    (tmp_path / "data" / "source" / "README.md").write_text("Put the files here.\n")
    with pytest.raises(StageError) as raised:
        stage_acquire(ctx)
    message = str(raised.value)
    assert raised.value.exit_code == 10
    assert "no .csv or .zip files" in message and "data/source" in message
    assert "Mendeley Data" in message and "data/README.md" in message
    assert "--source-dir" in message and "--sample" in message


def test_sample_is_generated_once_and_recorded_as_active(
    tmp_path: Path, calendar: TradingCalendar
) -> None:
    raw = tmp_path / "raw"
    first = acquire_sample(raw, calendar)
    assert first.copied and first.mode == "sample"
    assert not acquire_sample(raw, calendar).copied
    write_active(raw, first)
    active = read_active(raw)
    assert active.mode == "sample" and active.manifests == first.manifests
    manifest = read_manifest(first.manifests[0])
    assert manifest.retrieved_at is None  # byte-stable manifest
    assert manifest.source is SourceKind.SAMPLE


def test_read_active_without_data(tmp_path: Path) -> None:
    with pytest.raises(AcquireError, match="no acquired data"):
        read_active(tmp_path)


def test_same_names_in_different_folders_stay_apart(tmp_path: Path) -> None:
    source = tmp_path / "src"
    for part in ("a", "b"):
        (source / part).mkdir(parents=True)
        (source / part / "NSE_data_all_stocks_2099.csv").write_text(
            f"Date,Code\n{part}\n", encoding="utf-8"
        )
    manifest = read_manifest(acquire_local(tmp_path / "raw", source).manifests[0])
    names = sorted(f.name for f in manifest.files)
    assert len(set(names)) == 2 and "NSE_data_all_stocks_2099.csv" in names
    assert all(n.endswith("NSE_data_all_stocks_2099.csv") for n in names)


def test_windows_line_endings_copy_and_hash_as_lf(tmp_path: Path) -> None:
    """A CRLF download hashes like the same file with LF line endings, zips included."""
    lf = b"Date,Code\n2-Jan-99,AAA\n"
    for name, data in (("lf", lf), ("crlf", lf.replace(b"\n", b"\r\n"))):
        source = tmp_path / name
        source.mkdir()
        (source / "NSE_data_all_stocks_2099.csv").write_bytes(data)
        with zipfile.ZipFile(source / "pack.zip", "w") as archive:
            archive.writestr("inner/NSE_data_all_stocks_2098.csv", data)
    assert content_sha256(tmp_path / "crlf" / "NSE_data_all_stocks_2099.csv") == sha256_bytes(lf)

    def csv_entries(name: str) -> dict[str, str]:
        result = acquire_local(tmp_path / f"raw-{name}", tmp_path / name)
        folder = result.manifests[0].parent
        manifest = read_manifest(result.manifests[0])
        for entry in manifest.files:
            if entry.name.endswith(".csv"):
                assert (folder / entry.name).read_bytes() == lf  # the copy itself is LF
        return {f.name: f.sha256 for f in manifest.files if f.name.endswith(".csv")}

    assert (
        csv_entries("crlf")
        == csv_entries("lf")
        == {
            "NSE_data_all_stocks_2099.csv": sha256_bytes(lf),
            "NSE_data_all_stocks_2098.csv": sha256_bytes(lf),
        }
    )


def test_a_crlf_copy_still_matches_its_correction(
    tmp_path: Path, calendar: TradingCalendar, repo_root: Path
) -> None:
    """Corrections are keyed to the LF hash; a copy with Windows line endings matches too."""
    generate(tmp_path / "sample", calendar)
    planted = (tmp_path / "sample" / "NSE_data_all_stocks_2017.csv").read_bytes()
    windows = tmp_path / "windows"
    windows.mkdir()
    (windows / "NSE_data_all_stocks_2017.csv").write_bytes(planted.replace(b"\n", b"\r\n"))
    (entry,) = read_manifest(acquire_local(tmp_path / "raw", windows).manifests[0]).files
    rules = load_corrections(repo_root / "reference" / "corrections.yaml").corrections
    assert entry.sha256 == next(r.sha256 for r in rules if r.id == "SAMPLE-01")


def test_a_licence_edit_refreshes_the_record_without_copying(
    tmp_path: Path, repo_root: Path
) -> None:
    import dataclasses

    source = make_folder(tmp_path)
    citation = load_citation(repo_root / "reference" / "mendeley.yaml")
    raw = tmp_path / "raw"
    acquire_dataset(raw, source, citation)
    licensed = dataclasses.replace(citation, licence="CC BY 4.0")
    result = acquire_dataset(raw, source, licensed)
    assert not result.copied
    assert read_manifest(result.manifests[0]).licence == "CC BY 4.0"
