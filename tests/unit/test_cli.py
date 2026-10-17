"""The command line (§3): usage errors, guidance when inputs are missing, exit codes (§3.3)."""

from __future__ import annotations

from pathlib import Path

from nsefc import __version__
from tests.conftest import cli


def test_version(tmp_path: Path) -> None:
    result = cli(["--version"], tmp_path)
    assert result.exit_code == 0 and __version__ in result.output


def test_usage_errors_exit_2(tmp_path: Path) -> None:
    assert cli(["run", "--sample", "--source-dir", str(tmp_path)], tmp_path).exit_code == 2
    assert cli(["run", "--profile", "turbo", "--no-serve"], tmp_path).exit_code == 2


def test_stages_explain_missing_inputs(tmp_path: Path) -> None:
    for command in (["ingest"], ["train"], ["predict"], ["publish"]):
        result = cli(command, tmp_path)
        assert result.exit_code == 2, command
        assert "run" in result.output, command


def test_missing_dataset_folder_exits_10(tmp_path: Path) -> None:
    result = cli(["acquire", "--source-dir", str(tmp_path / "nowhere")], tmp_path)
    assert result.exit_code == 10
    assert "--sample" in result.output


def test_status_and_serve_before_any_run(tmp_path: Path) -> None:
    assert "No data yet" in cli(["status"], tmp_path).output
    result = cli(["serve", "--no-browser"], tmp_path)
    assert result.exit_code == 2 and "No results yet" in result.output


def test_import_needs_a_dataset_first(tmp_path: Path) -> None:
    csv = tmp_path / "new.csv"
    csv.write_text("date,ticker,close,volume\n2025-11-03,SCOM,28.4,100\n", encoding="utf-8")
    result = cli(["import", str(csv)], tmp_path / "data")
    assert result.exit_code == 2 and "before importing" in result.output


def test_maintainer_checks_pass_on_a_clean_tree(tmp_path: Path) -> None:
    assert cli(["dev", "contract", "--check"], tmp_path).exit_code == 0
    assert cli(["dev", "web-hash", "--check"], tmp_path).exit_code == 0
    assert "Mashujaa" in cli(["dev", "calendar", "2025"], tmp_path).output


def test_import_round_trip(tmp_path: Path) -> None:
    """§5.5: imports add later sessions, are labelled, and may not overlap."""
    from nsefc.storage import read_json
    from tests.unit.test_ingest import GOLDEN

    source = tmp_path / "dataset"
    source.mkdir()
    (source / "NSE_data_all_stocks_2025.csv").write_text(GOLDEN, encoding="utf-8")
    data = tmp_path / "data"
    assert cli(["acquire", "--source-dir", str(source)], data).exit_code == 0
    assert cli(["ingest"], data).exit_code == 0
    new = tmp_path / "new.csv"
    new.write_text(
        "date,ticker,close,volume\n2025-01-08,KUKZ,396,700\n2025-01-08,EGAD,13,0\n",
        encoding="utf-8",
    )
    result = cli(["import", str(new)], data)
    assert result.exit_code == 0 and "Imported 2 rows" in result.output
    assert cli(["import", str(new)], data).exit_code == 20  # the same sessions again
    old = tmp_path / "old.csv"
    old.write_text("date,ticker,close,volume\n2025-01-07,KUKZ,396,700\n", encoding="utf-8")
    rejected = cli(["import", str(old)], data)
    assert rejected.exit_code == 20 and "on or before" in rejected.output
    assert cli(["ingest"], data).exit_code == 0
    report = read_json(data / "canonical" / "ingest_report.json")
    assert report["data_mode"] == "historical+imports" and report["last_session"] == "2025-01-08"
    assert report["dataset_last_session"] == "2025-01-07"
