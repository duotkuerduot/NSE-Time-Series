"""Reader golden files, corrections and the ingest stage."""

from __future__ import annotations

import math
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from nsefc.acquire import Manifest
from nsefc.acquire.manifest import describe_files
from nsefc.calendar import TradingCalendar
from nsefc.domain import DataMode, SourceKind
from nsefc.ingest import CorrectionError, SchemaError, SourceFiles, ingest, read_import_file
from nsefc.ingest.reader import file_year, parse_date, parse_number, read_price_file
from nsefc.quality import DataQualityError
from nsefc.storage import sha256_file

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "historical"
HEADER = "Date,Code,Name,12m Low,12m High,Day Low,Day High,Day Price,Previous,Change,Change%,Volume,Adjusted Price\n"
GOLDEN = HEADER + (
    "2-Jan-25,KUKZ,Kakuzi Plc,365,440,385,400,392.5,385,7.5,1.95%,200,-\n"
    "2-Jan-25,EGAD,Eaagads Ltd,10.8,24.1,12,12,12,12,-,-,-,-\n"
    "2-Jan-25,^NASI,NSE All Share Index,90,130,123,123,123.4,122.9,0.5,0.41%,-,-\n"
    '3-Jan-25,KUKZ,Kakuzi Plc,365,440,385,395,390,392.5,-2.5,-0.64%,"1,100",-\n'
    "3-Jan-25,EGAD,Eaagads Ltd,10.8,24.1,12,12.5,12.5,12,0.5,4.17%,300,-\n"
    "3-Jan-25,EGAD,Eaagads Ltd,10.8,24.1,12,12.5,12.5,12,0.5,4.17%,300,-\n"
    "6-Jan-25,KUKZ,Kakuzi Plc,365,440,390,395,395,390,5,1.28%,500,-\n"
    "7-Jan-25,EGAD,Eaagads Ltd,10.8,24.1,12.5,13,13,12.5,0.5,4.00%,100,-\n"
    "7-Jan-25,KUKZ,Kakuzi Plc,365,440,394,396,395,395,-,-,-,-\n"
)


def source(folder: Path, files: dict[str, str], kind: SourceKind = SourceKind.LOCAL) -> SourceFiles:
    folder.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    return SourceFiles(Manifest(source=kind, files=describe_files(folder)), folder)


@pytest.fixture
def reference(tmp_path: Path, repo_root: Path) -> Path:
    """A reference folder with the real securities list and no corrections."""
    folder = tmp_path / "reference"
    folder.mkdir()
    shutil.copy(repo_root / "reference" / "securities.csv", folder / "securities.csv")
    (folder / "corrections.yaml").write_text("version: 1\ncorrections: []\n", encoding="utf-8")
    return folder


def run_ingest(sources: list[SourceFiles], calendar: TradingCalendar, reference: Path):  # type: ignore[no-untyped-def]
    return ingest(
        sources,
        calendar,
        reference_dir=reference,
        band=0.10,
        event_threshold=0.105,
        mkt_window=20,
        mkt_min_share=0.7,
        vwap_tolerance=0.02,
    )


# ---------------------------------------------------------------- reader
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2-Jan-25", date(2025, 1, 2)),
        ("31-Oct-2025", date(2025, 10, 31)),
        ("1/2/2007", date(2007, 1, 2)),
        (" 12/24/2007 ", date(2007, 12, 24)),
        ("", None),
        ("2025-01-02", None),
    ],
)
def test_parse_date_formats(raw: str, expected: date | None) -> None:
    assert parse_date(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"), [("1,234,500", 1_234_500.0), ("392.5", 392.5), ("1.95%", 1.95)]
)
def test_parse_number(raw: str, expected: float) -> None:
    assert parse_number(raw) == expected


@pytest.mark.parametrize("raw", ["-", "", "n/a"])
def test_parse_number_none(raw: str) -> None:
    assert math.isnan(parse_number(raw))


def test_file_year() -> None:
    assert file_year("NSE_data_all_stocks_2020_to_jun30.csv") == 2020
    assert file_year("NSE_data_all_stocks_2025_jan_to_oct.csv") == 2025
    assert file_year("prices.csv") is None


def test_reader_keeps_lines_and_reports_problems() -> None:
    path = FIXTURES / "NSE_data_all_stocks_2099_sample.csv"
    result = read_price_file(path, sha256="x" * 64, relative_name=path.name)
    rows = result.rows
    assert list(rows["line"]) == [2, 3, 4, 5, 6, 8]
    assert list(rows["code"]) == ["EGAD", "KUKZ", "^NASI", "KUKZ", "EGAD", "EGAD"]
    assert rows["session_date"].dt.date.tolist()[3] == date(2025, 1, 3)  # month-first format
    assert result.unparsed_dates == [(path.name, 7, "")]
    egad = rows.iloc[0]
    assert egad["close"] == 12 and math.isnan(egad["volume"])  # "-" means no trades


def test_reader_rejects_a_file_without_required_columns(tmp_path: Path) -> None:
    path = tmp_path / "NSE_data_all_stocks_2025.csv"
    path.write_text("Date,Code,Name\n2-Jan-25,AAA,A\n", encoding="utf-8")
    with pytest.raises(SchemaError, match="missing column"):
        read_price_file(path, sha256="x" * 64, relative_name=path.name)


# ---------------------------------------------------------------- the ingest stage
def test_golden_file_becomes_the_expected_canonical_panel(
    tmp_path: Path, calendar: TradingCalendar, reference: Path
) -> None:
    result = run_ingest(
        [source(tmp_path / "raw", {"NSE_data_all_stocks_2025.csv": GOLDEN})], calendar, reference
    )
    bars = result.bars.set_index(["ticker", "session_date"])
    nan = np.nan
    expected = (
        pd.DataFrame(
            [
                ("EGAD", "2025-01-02", 12.0, 0, False, False, nan, nan),
                ("EGAD", "2025-01-03", 12.5, 300, True, False, 12.5, 12.0),
                ("EGAD", "2025-01-06", 12.5, 0, False, True, nan, nan),  # carried forward
                ("EGAD", "2025-01-07", 13.0, 100, True, False, 13.0, 12.5),
                ("KUKZ", "2025-01-02", 392.5, 200, True, False, 400.0, 385.0),
                ("KUKZ", "2025-01-03", 390.0, 1100, True, False, 395.0, 385.0),
                ("KUKZ", "2025-01-06", 395.0, 500, True, False, 395.0, 390.0),
                ("KUKZ", "2025-01-07", 395.0, 0, False, False, nan, nan),  # untraded: no range
            ],
            columns=[
                "ticker",
                "session_date",
                "close",
                "volume",
                "traded",
                "is_carried_forward",
                "high",
                "low",
            ],
        )
        .assign(session_date=lambda f: pd.to_datetime(f["session_date"]))
        .set_index(["ticker", "session_date"])
    )
    pd.testing.assert_frame_equal(
        bars[expected.columns], expected, check_dtype=False, check_index_type=False
    )
    assert not bars["is_event"].any()
    assert result.counts["identical_duplicates_dropped"] == 1
    assert result.counts["held_sessions"] == 4 and result.counts["carried_forward_rows"] == 1
    assert result.indices[["index", "level"]].values.tolist() == [["^NASI", 123.4]]
    assert result.data_mode is DataMode.HISTORICAL
    lineage = result.bars["source_file_sha256"].unique().tolist()
    assert lineage == [sha256_file(tmp_path / "raw" / "NSE_data_all_stocks_2025.csv")]


def test_conflicting_duplicates_fail_key01(
    tmp_path: Path, calendar: TradingCalendar, reference: Path
) -> None:
    text = GOLDEN + "7-Jan-25,EGAD,Eaagads Ltd,10.8,24.1,12.5,13,13.5,12.5,0.5,4.00%,100,-\n"
    with pytest.raises(DataQualityError, match="KEY-01"):
        run_ingest(
            [source(tmp_path / "raw", {"NSE_data_all_stocks_2025.csv": text})], calendar, reference
        )


def test_a_misdated_row_fails_dat03(
    tmp_path: Path, calendar: TradingCalendar, reference: Path
) -> None:
    text = GOLDEN + "8-Jan-24,EGAD,Eaagads Ltd,10.8,24.1,12.5,13,13,12.5,-,-,100,-\n"
    with pytest.raises(DataQualityError, match="DAT-03"):
        run_ingest(
            [source(tmp_path / "raw", {"NSE_data_all_stocks_2025.csv": text})], calendar, reference
        )


def test_a_weekend_date_fails_dat01(
    tmp_path: Path, calendar: TradingCalendar, reference: Path
) -> None:
    text = GOLDEN + "4-Jan-25,EGAD,Eaagads Ltd,10.8,24.1,12.5,13,13,12.5,-,-,100,-\n"
    with pytest.raises(DataQualityError, match="DAT-01"):
        run_ingest(
            [source(tmp_path / "raw", {"NSE_data_all_stocks_2025.csv": text})], calendar, reference
        )


def test_an_unreadable_date_fails_sch01(
    tmp_path: Path, calendar: TradingCalendar, reference: Path
) -> None:
    text = GOLDEN + "someday,EGAD,Eaagads Ltd,10.8,24.1,12.5,13,13,12.5,-,-,100,-\n"
    with pytest.raises(SchemaError, match="SCH-01"):
        run_ingest(
            [source(tmp_path / "raw", {"NSE_data_all_stocks_2025.csv": text})], calendar, reference
        )


def test_sch02_excludes_bad_rows_without_stopping(
    tmp_path: Path, calendar: TradingCalendar, reference: Path
) -> None:
    text = GOLDEN + "8-Jan-25,EGAD,Eaagads Ltd,10.8,24.1,12.5,13,-,13,-,-,100,-\n"  # no price
    result = run_ingest(
        [source(tmp_path / "raw", {"NSE_data_all_stocks_2025.csv": text})], calendar, reference
    )
    sch02 = next(c for c in result.checks if c.id == "SCH-02")
    assert sch02.count == 1
    assert pd.Timestamp("2025-01-08") not in set(
        result.bars.loc[result.bars["ticker"] == "EGAD", "session_date"]
    )


# ---------------------------------------------------------------- corrections
def correction_yaml(
    sha: str, *, lines: tuple[int, int], from_: str, to: str, rule_id: str = "T-01"
) -> str:
    return (
        "version: 1\ncorrections:\n"
        f'  - id: {rule_id}\n    file: NSE_data_all_stocks_2025.csv\n    sha256: "{sha}"\n'
        f"    action: redate\n    lines: [{lines[0]}, {lines[1]}]\n    from: {from_}\n    to: {to}\n"
        "    reason: test\n"
    )


MISDATED = GOLDEN + (
    "11-Jan-25,EGAD,Eaagads Ltd,10.8,24.1,13,13,13,13,-,-,100,-\n"  # line 11: belongs to 8 Jan
    "11-Jan-25,KUKZ,Kakuzi Plc,365,440,395,396,396,395,1,0.25%,100,-\n"  # line 12
)


def test_redate_rule_applies_only_to_its_file(
    tmp_path: Path, calendar: TradingCalendar, reference: Path
) -> None:
    src = source(tmp_path / "raw", {"NSE_data_all_stocks_2025.csv": MISDATED})
    sha = src.manifest.files[0].sha256
    (reference / "corrections.yaml").write_text(
        correction_yaml(sha, lines=(11, 12), from_="2025-01-11", to="2025-01-08")
        + correction_yaml(
            "0" * 64, lines=(2, 3), from_="2025-01-02", to="2025-01-03", rule_id="OTHER"
        ).split("corrections:\n")[1],
        encoding="utf-8",
    )
    result = run_ingest([src], calendar, reference)
    assert [(a.rule.id, a.rows) for a in result.corrections.applied] == [("T-01", 2)]
    assert [r.id for r in result.corrections.not_applicable] == ["OTHER"]
    egad = result.bars[result.bars["ticker"] == "EGAD"].set_index("session_date")
    assert egad.loc[pd.Timestamp("2025-01-08"), "close"] == 13.0


def test_the_same_data_without_its_rule_fails(
    tmp_path: Path, calendar: TradingCalendar, reference: Path
) -> None:
    with pytest.raises(DataQualityError, match="DAT-01"):
        run_ingest(
            [source(tmp_path / "raw", {"NSE_data_all_stocks_2025.csv": MISDATED})],
            calendar,
            reference,
        )


def test_a_rule_that_matches_nothing_stops_the_ingest(
    tmp_path: Path, calendar: TradingCalendar, reference: Path
) -> None:
    src = source(tmp_path / "raw", {"NSE_data_all_stocks_2025.csv": MISDATED})
    (reference / "corrections.yaml").write_text(
        correction_yaml(
            src.manifest.files[0].sha256, lines=(2, 3), from_="2025-01-11", to="2025-01-08"
        ),
        encoding="utf-8",
    )
    with pytest.raises(CorrectionError, match="matches no rows"):
        run_ingest([src], calendar, reference)


def test_a_redate_onto_existing_rows_stops_the_ingest(
    tmp_path: Path, calendar: TradingCalendar, reference: Path
) -> None:
    src = source(tmp_path / "raw", {"NSE_data_all_stocks_2025.csv": MISDATED})
    (reference / "corrections.yaml").write_text(
        correction_yaml(
            src.manifest.files[0].sha256, lines=(11, 12), from_="2025-01-11", to="2025-01-07"
        ),
        encoding="utf-8",
    )
    with pytest.raises(CorrectionError, match="already has rows"):
        run_ingest([src], calendar, reference)


# ---------------------------------------------------------------- imports
IMPORT = "date,ticker,close,volume\n2025-01-08,KUKZ,396,700\n2025-01-08,EGAD,13,0\n"


def test_imports_extend_the_dataset(
    tmp_path: Path, calendar: TradingCalendar, reference: Path
) -> None:
    dataset = source(tmp_path / "raw", {"NSE_data_all_stocks_2025.csv": GOLDEN})
    imports = source(tmp_path / "imports", {"a.csv": IMPORT}, SourceKind.USER_IMPORT)
    result = run_ingest([dataset, imports], calendar, reference)
    assert result.data_mode is DataMode.HISTORICAL_WITH_IMPORTS
    assert result.dataset_last_session == pd.Timestamp("2025-01-07")
    assert result.counts["imported_rows"] == 2
    kukz = result.bars[result.bars["ticker"] == "KUKZ"].set_index("session_date")
    assert kukz.loc[pd.Timestamp("2025-01-08"), "close"] == 396
    assert kukz.loc[pd.Timestamp("2025-01-08"), "source"] == "user_import"


def test_imports_may_not_overlap_the_dataset(
    tmp_path: Path, calendar: TradingCalendar, reference: Path
) -> None:
    dataset = source(tmp_path / "raw", {"NSE_data_all_stocks_2025.csv": GOLDEN})
    overlapping = "date,ticker,close,volume\n2025-01-07,SCOM,20,100\n"
    imports = source(tmp_path / "imports", {"a.csv": overlapping}, SourceKind.USER_IMPORT)
    with pytest.raises(DataQualityError, match="IMP-01"):
        run_ingest([dataset, imports], calendar, reference)


def test_import_files_need_iso_dates_and_columns(tmp_path: Path) -> None:
    bad_date = tmp_path / "a.csv"
    bad_date.write_text("date,ticker,close,volume\n8/1/2025,KUKZ,396,700\n", encoding="utf-8")
    with pytest.raises(SchemaError, match="YYYY-MM-DD"):
        read_import_file(bad_date, sha256="x" * 64, relative_name="a.csv")
    missing = tmp_path / "b.csv"
    missing.write_text("date,ticker,close\n2025-01-08,KUKZ,396\n", encoding="utf-8")
    with pytest.raises(SchemaError, match="needs columns"):
        read_import_file(missing, sha256="x" * 64, relative_name="b.csv")
