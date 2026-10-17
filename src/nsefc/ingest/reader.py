"""Reader for the Mendeley "NSE All Stocks Prices" CSV format (docs/data/mendeley-dataset.md).

Every daily price file has one row per security per session with these columns (header case
varies between files): ``Date, Code, Name, 12m Low, 12m High, Day Low, Day High, Day Price,
Previous, Change, Change%, Volume, Adjust[ed Price]``. Dates come in three formats
(``2-Jan-25``, ``2-Jan-2025`` and month-first ``1/2/2007``), numbers use thousands separators,
and ``-`` means "none" (a volume of ``-`` means the security did not trade). Index levels
share the files, with codes starting with ``^``.

The reader keeps every row's file and line number, so corrections and the data audit can point
at the exact source of each value (G-5).
"""

from __future__ import annotations

import csv
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

DATE_FORMATS = ("%d-%b-%y", "%d-%b-%Y", "%m/%d/%Y")
PRICE_FILE_GLOB = "NSE_data_all_stocks_*.csv"
SECTOR_FILE_GLOB = "NSE_data_stock_market_sectors_*.csv"

# Canonical name -> accepted header spellings (compared case-insensitively).
COLUMNS = {
    "date": ("date",),
    "code": ("code",),
    "name": ("name",),
    "low": ("day low",),
    "high": ("day high",),
    "close": ("day price",),
    "previous": ("previous",),
    "volume": ("volume",),
}
OPTIONAL_COLUMNS = {"turnover": ("turnover", "value traded"), "open": ("open", "day open")}
SECTOR_COLUMNS = {
    "sector": ("sector",),
    "code": ("code", "stock_code"),
    "name": ("name", "stock_name"),
}


class SchemaError(ValueError):
    """SCH-01: a file lacks a required column (the run stops, exit code 20)."""


def parse_date(raw: str) -> date | None:
    text = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()  # noqa: DTZ007 - a date, no time part
        except ValueError:
            continue
    return None


def parse_number(raw: str) -> float:
    """'1,234,500' -> 1234500.0; '1.95%' -> 1.95; '-' or '' -> NaN."""
    text = raw.strip().replace(",", "").removesuffix("%")
    if text in {"", "-"}:
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def _column_index(header: list[str], spellings: Mapping[str, Sequence[str]]) -> dict[str, int]:
    lowered = [h.strip().lower() for h in header]
    found: dict[str, int] = {}
    for name, options in spellings.items():
        for option in options:
            if option in lowered:
                found[name] = lowered.index(option)
                break
    return found


def file_year(name: str) -> int | None:
    """The year a file says it covers ("NSE_data_all_stocks_2017.csv" -> 2017)."""
    match = re.search(r"(19|20)\d{2}", name)
    return int(match.group(0)) if match else None


@dataclass(slots=True)
class ReadResult:
    rows: pd.DataFrame
    blank_rows: int = 0
    unparsed_dates: list[tuple[str, int, str]] = field(default_factory=list)


def read_price_file(path: Path, *, sha256: str, relative_name: str) -> ReadResult:
    """One price file -> a frame of raw rows (strings parsed; nothing corrected yet)."""
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise SchemaError(f"{relative_name}: empty file") from exc
        index = _column_index(header, COLUMNS)
        missing = sorted(set(COLUMNS) - set(index))
        if missing:
            raise SchemaError(f"{relative_name}: missing column(s) {missing}; header was {header}")
        optional = _column_index(header, OPTIONAL_COLUMNS)
        records: list[tuple[object, ...]] = []
        blank = 0
        unparsed: list[tuple[str, int, str]] = []
        width = max([*index.values(), *optional.values()]) + 1
        for line_number, row in enumerate(reader, start=2):
            if not any(cell.strip() for cell in row):
                blank += 1
                continue
            if len(row) < width:
                row = row + [""] * (width - len(row))
            day = parse_date(row[index["date"]])
            if day is None:
                unparsed.append((relative_name, line_number, row[index["date"]]))
                continue
            records.append(
                (
                    relative_name,
                    sha256,
                    line_number,
                    day,
                    row[index["code"]].strip(),
                    row[index["name"]].strip(),
                    parse_number(row[index["close"]]),
                    parse_number(row[index["previous"]]),
                    parse_number(row[index["low"]]),
                    parse_number(row[index["high"]]),
                    parse_number(row[index["volume"]]),
                    parse_number(row[optional["turnover"]]) if "turnover" in optional else np.nan,
                    parse_number(row[optional["open"]]) if "open" in optional else np.nan,
                )
            )
    frame = pd.DataFrame.from_records(
        records,
        columns=[
            "source_file",
            "source_file_sha256",
            "line",
            "session_date",
            "code",
            "name",
            "close",
            "previous",
            "low",
            "high",
            "volume",
            "turnover",
            "open",
        ],
    )
    frame["session_date"] = pd.to_datetime(frame["session_date"])
    return ReadResult(frame, blank, unparsed)


def read_sector_file(path: Path) -> pd.DataFrame:
    """code -> sector, from the dataset's sector files (two header spellings)."""
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, [])
        index = _column_index(header, SECTOR_COLUMNS)
        if set(index) != set(SECTOR_COLUMNS):
            return pd.DataFrame(columns=["code", "sector", "name"])
        rows = [
            (r[index["code"]].strip(), r[index["sector"]].strip(), r[index["name"]].strip())
            for r in reader
            if len(r) > max(index.values()) and r[index["code"]].strip()
        ]
    return pd.DataFrame(rows, columns=["code", "sector", "name"])


def is_price_file(name: str) -> bool:
    return Path(name).match(PRICE_FILE_GLOB)


def is_sector_file(name: str) -> bool:
    return Path(name).match(SECTOR_FILE_GLOB)
