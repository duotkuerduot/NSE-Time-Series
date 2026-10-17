"""Local files only (§6.1): atomic writes, folder swaps, safe paths and date-typed tables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

from nsefc.storage import (
    DataLayout,
    UnsafePathError,
    atomic_write_json,
    clean_stale_temporaries,
    read_json,
    read_table,
    safe_join,
    sha256_text,
    staged_dir,
    write_table,
)


def test_atomic_json_round_trip(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b.json"
    atomic_write_json(target, {"x": 1, "y": [1, 2]})
    assert read_json(target) == {"x": 1, "y": [1, 2]}
    assert [p.name for p in target.parent.iterdir()] == ["b.json"]


def fail_inside(final: Path) -> None:
    with staged_dir(final) as staged:
        (staged / "two.json").write_text("2", encoding="utf-8")
        raise RuntimeError("stage failed")


def test_staged_dir_swaps_in_complete_folders_only(tmp_path: Path) -> None:
    final = tmp_path / "release"
    with staged_dir(final) as staged:
        (staged / "one.json").write_text("1", encoding="utf-8")
    assert (final / "one.json").read_text(encoding="utf-8") == "1"
    with pytest.raises(RuntimeError, match="stage failed"):
        fail_inside(final)
    # The failed attempt left the previous folder untouched and no temporary folder behind.
    assert sorted(p.name for p in final.iterdir()) == ["one.json"]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["release"]
    with staged_dir(final) as staged:
        (staged / "three.json").write_text("3", encoding="utf-8")
    assert sorted(p.name for p in final.iterdir()) == ["three.json"]


def test_clean_stale_temporaries(tmp_path: Path) -> None:
    (tmp_path / ".tmp-x").mkdir()
    (tmp_path / ".old-y").write_text("", encoding="utf-8")
    (tmp_path / "keep").write_text("", encoding="utf-8")
    assert clean_stale_temporaries(tmp_path) == 2
    assert [p.name for p in tmp_path.iterdir()] == ["keep"]


@pytest.mark.parametrize("bad", ["../x", "a/../../x", "/etc/passwd", "..\\x", "a/..\\..\\x"])
def test_safe_join_refuses_escapes(tmp_path: Path, bad: str) -> None:
    with pytest.raises(UnsafePathError):
        safe_join(tmp_path, bad)


def test_safe_join_allows_children(tmp_path: Path) -> None:
    assert (
        safe_join(tmp_path, "r/x/status.json") == (tmp_path / "r" / "x" / "status.json").resolve()
    )
    assert safe_join(tmp_path, "") == tmp_path.resolve()


def test_session_columns_are_stored_as_dates(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "ticker": ["A", "B"],
            "session_date": pd.to_datetime(["2025-10-30", "2025-10-31"]),
            "target_session": pd.to_datetime(["2025-10-31", "2025-11-03"]),
            "close": [1.0, 2.0],
        }
    )
    path = tmp_path / "t.parquet"
    write_table(frame, path)
    schema = pq.read_schema(path)
    assert str(schema.field("session_date").type) == "date32[day]"
    assert str(schema.field("target_session").type) == "date32[day]"
    back = read_table(path)
    pd.testing.assert_series_equal(back["session_date"], frame["session_date"], check_dtype=False)
    assert pd.api.types.is_datetime64_any_dtype(back["target_session"])


def test_layout_names_every_folder(tmp_path: Path) -> None:
    layout = DataLayout(tmp_path)
    assert layout.bars == tmp_path / "canonical" / "bars.parquet"
    assert layout.api == tmp_path / "api" / "v1"
    assert layout.stamp("train") == tmp_path / "stamps" / "train.json"
    assert layout.latest_run == tmp_path / "runs" / "latest.json"


def test_sha256_text_separates_parts() -> None:
    assert sha256_text("ab", "c") != sha256_text("a", "bc")
