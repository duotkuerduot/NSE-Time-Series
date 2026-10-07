"""Reader for the repository's historical dataset ("NSE Data", Mendeley Data, CC BY 4.0).

Phase 0 needs only the session dates (calendar reconciliation) and a coverage profile.
The full HistoricalFileProvider, which normalises rows through the data-quality gate,
arrives in Phase 1 (ENGINEERING.md 8.4).
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from nsefc.domain import MAIN_BOARD_PRICE_BAND, MIN_PRICE_SETTING_VOLUME

# The files mix three date formats: "2-Jan-25", "2-Jan-2025" and "1/2/2007" (month first).
DATE_FORMATS = ("%d-%b-%y", "%d-%b-%Y", "%m/%d/%Y")
PROVIDER_ID = "historical_file"
TICK = 0.01  # smallest printed price step: the tolerance for rounding at the band edge


def parse_date(raw: str) -> date | None:
    text = raw.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()  # noqa: DTZ007 - a date, no time part
        except ValueError:
            continue
    return None


def price_files(data_dir: Path) -> list[Path]:
    """The daily price files (sector files are separate reference data)."""
    return sorted(p for p in Path(data_dir).rglob("NSE_data_all_stocks_*.csv"))


@dataclass(slots=True)
class FileProfile:
    path: Path
    header: list[str]
    rows: int = 0
    unparsed_dates: int = 0
    equity_codes: set[str] = field(default_factory=set)
    index_codes: set[str] = field(default_factory=set)
    dates: Counter[date] = field(default_factory=Counter)
    duplicate_keys: int = 0

    @property
    def first(self) -> date | None:
        return min(self.dates) if self.dates else None

    @property
    def last(self) -> date | None:
        return max(self.dates) if self.dates else None


def _rows(path: Path) -> Iterator[tuple[list[str], list[str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = [h.strip() for h in next(reader)]
        for row in reader:
            if row:
                yield header, row


def profile_file(path: Path) -> FileProfile:
    profile: FileProfile | None = None
    seen: Counter[tuple[date, str]] = Counter()
    for header, row in _rows(path):
        if profile is None:
            profile = FileProfile(path=path, header=header)
        profile.rows += 1
        day = parse_date(row[0])
        if day is None:
            profile.unparsed_dates += 1
            continue
        code = row[1].strip()
        if code.startswith("^"):
            profile.index_codes.add(code)
            continue
        profile.equity_codes.add(code)
        profile.dates[day] += 1
        seen[(day, code)] += 1
    if profile is None:
        return FileProfile(path=path, header=[])
    profile.duplicate_keys = sum(1 for count in seen.values() if count > 1)
    return profile


def traded_dates(paths: Iterable[Path]) -> set[date]:
    """Dates on which at least one equity row exists."""
    found: set[date] = set()
    for path in paths:
        found.update(profile_file(path).dates)
    return found


def parse_number(raw: str) -> float | None:
    """'1,234,500' -> 1234500.0, '1.95%' -> 1.95, '-' or '' -> None."""
    text = raw.strip().replace(",", "").removesuffix("%")
    if text in {"", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class DailyMove:
    """One equity row's Day Price against the Previous price printed beside it."""

    session_date: date
    code: str
    previous: float
    price: float
    volume: int

    @property
    def change(self) -> float:
        return self.price / self.previous - 1

    @property
    def price_set(self) -> bool:
        """At least 100 shares traded, so the session set a new official price (Rule 7.6.6)."""
        return self.volume >= MIN_PRICE_SETTING_VOLUME

    def beyond_band(self, band: float = MAIN_BOARD_PRICE_BAND) -> bool:
        """Further from the previous price than the band allows, by more than one tick."""
        return abs(self.price - self.previous) > band * self.previous + TICK + 1e-9


def _price_columns(header: list[str]) -> tuple[int, int, int] | None:
    lowered = [h.strip().lower() for h in header]
    try:
        return lowered.index("day price"), lowered.index("previous"), lowered.index("volume")
    except ValueError:
        return None


def daily_moves(paths: Iterable[Path]) -> Iterator[DailyMove]:
    """Equity rows with a positive Day Price and Previous; a volume of "-" counts as zero.

    The first row wins when a (date, code) pair repeats.
    """
    seen: set[tuple[date, str]] = set()
    for path in paths:
        columns: tuple[int, int, int] | None = None
        for header, row in _rows(path):
            if columns is None:
                columns = _price_columns(header)
                if columns is None:
                    break
            if len(row) <= max(columns):
                continue
            day = parse_date(row[0])
            code = row[1].strip()
            if day is None or not code or code.startswith("^") or (day, code) in seen:
                continue
            price, previous, volume = (parse_number(row[i]) for i in columns)
            if price is None or previous is None or price <= 0 or previous <= 0:
                continue
            seen.add((day, code))
            yield DailyMove(day, code, previous, price, int(volume or 0))
