from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from nsefc.ingestion.providers.historical_file import (
    daily_moves,
    parse_date,
    parse_number,
    price_files,
    profile_file,
    traded_dates,
)
from nsefc.pipeline.reports import coverage_markdown

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "historical"


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


def test_profile_counts_equities_indices_and_problems() -> None:
    (path,) = price_files(FIXTURES)
    profile = profile_file(path)
    assert profile.header[0] == "Date"  # byte-order mark stripped
    assert profile.equity_codes == {"EGAD", "KUKZ"}
    assert profile.index_codes == {"^NASI"}
    assert profile.unparsed_dates == 1
    assert profile.duplicate_keys == 1
    assert traded_dates([path]) == {date(2025, 1, 2), date(2025, 1, 3)}


def test_coverage_report_renders() -> None:
    text = coverage_markdown(FIXTURES)
    assert "| NSE_data_all_stocks_2099_sample.csv |" in text
    assert "## Sessions per month" in text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("1,234,500", 1_234_500.0), ("392.5", 392.5), ("1.95%", 1.95), ("-", None), ("", None)],
)
def test_parse_number(raw: str, expected: float | None) -> None:
    assert parse_number(raw) == expected


MOVES_CSV = (
    "DATE,CODE,NAME,12m Low,12m High,Day Low,Day High,Day Price,Previous,Change,Change%,"
    "Volume,Adjust\n"
    # exactly +10%: inside the band
    '2-Jan-25,SCOM,Safaricom Plc,10,20,15,16.5,16.5,15,1.5,10.00%,"1,234,500",-\n'
    # +10.3% at a price of 0.29: inside, because of the one-tick tolerance
    '2-Jan-25,LOWP,Low Price Ltd,0.2,0.5,0.32,0.32,0.32,0.29,0.03,10.34%,"10,000",-\n'
    # +12.1% on 99 shares: beyond the band, not price-setting
    "3-Jan-25,SCOM,Safaricom Plc,10,20,16.5,18.5,18.5,16.5,2,12.12%,99,-\n"
    # -50% (a bonus issue, say): beyond the band and price-setting
    '6-Jan-25,BONU,Bonus Co,4,20,5,5,5,10,-5,-50.00%,"2,000",-\n'
    # index rows are ignored
    "6-Jan-25,^NASI,NSE All Share Index,90,130,123,140,140,120,20,16.67%,-,-\n"
    # no trades: volume "-" counts as zero; the repeated key keeps the first row
    "6-Jan-25,EGAD,Eaagads Ltd,10.8,24.1,12,12,12,12,-,-,-,-\n"
    "6-Jan-25,EGAD,Eaagads Ltd,10.8,24.1,12,12,99,12,-,-,-,-\n"
    # no day price: skipped
    "7-Jan-25,NOPX,No Price Ltd,1,2,-,-,-,1.5,-,-,-,-\n"
)


def test_daily_moves_against_the_band(tmp_path: Path) -> None:
    (tmp_path / "NSE_data_all_stocks_2098.csv").write_text(MOVES_CSV, encoding="utf-8")
    moves = {(m.code, m.session_date.day): m for m in daily_moves(price_files(tmp_path))}
    assert set(moves) == {("SCOM", 2), ("LOWP", 2), ("SCOM", 3), ("BONU", 6), ("EGAD", 6)}
    assert {key for key, m in moves.items() if m.beyond_band()} == {("SCOM", 3), ("BONU", 6)}
    assert {key for key, m in moves.items() if m.price_set} == {
        ("SCOM", 2),
        ("LOWP", 2),
        ("BONU", 6),
    }
    assert moves[("EGAD", 6)].price == 12
    assert moves[("EGAD", 6)].volume == 0
    assert moves[("BONU", 6)].change == pytest.approx(-0.5)


def test_coverage_report_shows_band_check(tmp_path: Path) -> None:
    (tmp_path / "NSE_data_all_stocks_2098.csv").write_text(MOVES_CSV, encoding="utf-8")
    text = coverage_markdown(tmp_path)
    assert "| 2025 | 5 | 3 | 2 | 1 |" in text
    assert "66.667% of price-setting rows lie within the band." in text
    largest = text.split("### Largest moves beyond the band (2 of 2)")[1]
    assert largest.index("| BONU |") < largest.index("| SCOM |")
    assert "| 2025-01-06 | BONU | 10.00 | 5.00 | -50.0% | 2,000 |" in largest
