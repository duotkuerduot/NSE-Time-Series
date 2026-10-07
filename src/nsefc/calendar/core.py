"""Trading calendar and session arithmetic (ENGINEERING.md 7.5).

Every module asks this one for sessions; nobody computes "tomorrow" with date arithmetic.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

SATURDAY, SUNDAY = 5, 6


class CalendarError(ValueError):
    """The calendar specification is invalid."""


class CalendarCoverageError(LookupError):
    """A date outside the calendar's coverage was requested; extend the YAML first."""


class HolidayKind(StrEnum):
    FIXED = "fixed"
    EASTER = "easter"
    DATED = "dated"
    CLOSURE = "closure"


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FixedRule(_Spec):
    name: str
    month: int = Field(ge=1, le=12)
    day: int = Field(ge=1, le=31)
    since: int | None = None
    until: int | None = None
    source: str = "Public Holidays Act"

    def applies(self, year: int) -> bool:
        return (self.since is None or year >= self.since) and (
            self.until is None or year <= self.until
        )


class EasterRule(_Spec):
    name: str
    offset_days: int


Status = Literal["confirmed", "listed", "provisional"]


class DatedEntry(_Spec):
    date: dt.date
    name: str
    status: Status
    source: str


class HeldSession(_Spec):
    """A weekday the rules would close but on which the market traded (data wins, 7.5)."""

    date: dt.date
    status: Literal["confirmed"]
    source: str


class Coverage(_Spec):
    start: date
    end: date


class CalendarSpec(_Spec):
    version: int
    timezone: Literal["Africa/Nairobi"]
    coverage: Coverage
    sunday_rule: Literal["next_free_weekday"]
    fixed: list[FixedRule]
    easter: list[EasterRule]
    dated: list[DatedEntry] = Field(default_factory=list)
    closures: list[DatedEntry] = Field(default_factory=list)
    held_sessions: list[HeldSession] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> CalendarSpec:
        if self.coverage.end < self.coverage.start:
            raise ValueError("coverage.end is before coverage.start")
        seen: set[date] = set()
        for entry in [*self.dated, *self.closures]:
            if entry.date in seen:
                raise ValueError(f"{entry.date} is entered twice")
            seen.add(entry.date)
            if not self.coverage.start <= entry.date <= self.coverage.end:
                raise ValueError(f"{entry.date} ({entry.name}) is outside coverage")
            if entry.date.weekday() >= SATURDAY and entry.status == "confirmed":
                raise ValueError(f"{entry.date} is a weekend; confirmed closures are weekdays")
        for held in self.held_sessions:
            if held.date in seen:
                raise ValueError(f"{held.date} is listed both as a closure and as a held session")
            seen.add(held.date)
            if held.date.weekday() >= SATURDAY:
                raise ValueError(f"held session {held.date} is a weekend")
            if not self.coverage.start <= held.date <= self.coverage.end:
                raise ValueError(f"held session {held.date} is outside coverage")
        return self


@dataclass(frozen=True, slots=True)
class Holiday:
    """A weekday on which the market is closed (or a weekend holiday, for completeness)."""

    date: dt.date
    name: str
    kind: HolidayKind
    status: str
    source: str
    observed_for: dt.date | None = None  # the Sunday this closure stands in for

    @property
    def closes_market(self) -> bool:
        return self.date.weekday() < SATURDAY


def easter_sunday(year: int) -> date:
    """Gregorian Easter Sunday (anonymous Gregorian algorithm, Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _as_date(value: date) -> date:
    # Session dates are plain local dates; a timestamp here is a bug (7.5 "Time handling").
    if isinstance(value, datetime):
        raise TypeError(
            "pass a datetime.date, not a datetime; never derive sessions from timestamps"
        )
    return value


class TradingCalendar:
    def __init__(self, spec: CalendarSpec) -> None:
        self.spec = spec
        self._years: dict[int, dict[date, Holiday]] = {}

    @classmethod
    def from_yaml(cls, path: Path) -> TradingCalendar:
        try:
            raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
            return cls(CalendarSpec.model_validate(raw))
        except (OSError, yaml.YAMLError, ValueError) as exc:
            raise CalendarError(f"cannot load calendar {path}: {exc}") from exc

    # ------------------------------------------------------------------ coverage
    @property
    def coverage_start(self) -> date:
        return self.spec.coverage.start

    @property
    def coverage_end(self) -> date:
        return self.spec.coverage.end

    def _check(self, day: date) -> date:
        day = _as_date(day)
        if not self.coverage_start <= day <= self.coverage_end:
            raise CalendarCoverageError(
                f"{day} is outside calendar coverage {self.coverage_start}..{self.coverage_end}"
            )
        return day

    def days_of_coverage_left(self, today: date) -> int:
        return (self.coverage_end - _as_date(today)).days

    # ------------------------------------------------------------------ holidays
    def _base_holidays(self, year: int) -> list[Holiday]:
        found: list[Holiday] = []
        for rule in self.spec.fixed:
            if rule.applies(year):
                found.append(
                    Holiday(
                        date(year, rule.month, rule.day),
                        rule.name,
                        HolidayKind.FIXED,
                        "rule",
                        rule.source,
                    )
                )
        sunday = easter_sunday(year)
        for easter in self.spec.easter:
            found.append(
                Holiday(
                    sunday + timedelta(days=easter.offset_days),
                    easter.name,
                    HolidayKind.EASTER,
                    "rule",
                    "Public Holidays Act",
                )
            )
        for entry in self.spec.dated:
            if entry.date.year == year:
                found.append(
                    Holiday(entry.date, entry.name, HolidayKind.DATED, entry.status, entry.source)
                )
        for entry in self.spec.closures:
            if entry.date.year == year:
                found.append(
                    Holiday(entry.date, entry.name, HolidayKind.CLOSURE, entry.status, entry.source)
                )
        return found

    def _year(self, year: int) -> dict[date, Holiday]:
        cached = self._years.get(year)
        if cached is not None:
            return cached
        base = sorted(self._base_holidays(year), key=lambda h: (h.date, h.name))
        taken = {h.date for h in base}
        result: dict[date, Holiday] = {}
        for holiday in base:
            if holiday.date.weekday() == SUNDAY:
                observed = holiday.date + timedelta(days=1)
                while observed.weekday() >= SATURDAY or observed in taken:
                    observed += timedelta(days=1)
                taken.add(observed)
                holiday = Holiday(
                    observed,
                    f"{holiday.name} (observed)",
                    holiday.kind,
                    holiday.status,
                    holiday.source,
                    observed_for=holiday.date,
                )
            existing = result.get(holiday.date)
            if existing is not None:
                holiday = Holiday(
                    holiday.date,
                    f"{existing.name}; {holiday.name}",
                    existing.kind,
                    existing.status,
                    existing.source,
                    existing.observed_for,
                )
            result[holiday.date] = holiday
        for held in self.spec.held_sessions:  # the market traded despite the rules
            result.pop(held.date, None)
        self._years[year] = result
        return result

    def holidays(self, year: int, *, weekdays_only: bool = True) -> list[Holiday]:
        if not self.coverage_start.year <= year <= self.coverage_end.year:
            raise CalendarCoverageError(f"{year} is outside calendar coverage")
        items = sorted(self._year(year).values(), key=lambda h: h.date)
        return [h for h in items if h.closes_market] if weekdays_only else items

    def holiday_on(self, day: date) -> Holiday | None:
        day = self._check(day)
        return self._year(day.year).get(day)

    # ------------------------------------------------------------------ sessions
    def is_scheduled_session(self, day: date) -> bool:
        day = self._check(day)
        return day.weekday() < SATURDAY and day not in self._year(day.year)

    def next_session(self, day: date) -> date:
        """The first scheduled session strictly after ``day``."""
        current = self._check(day) + timedelta(days=1)
        while not self.is_scheduled_session(current):
            current += timedelta(days=1)
        return current

    def previous_session(self, day: date) -> date:
        """The last scheduled session strictly before ``day``."""
        current = self._check(day) - timedelta(days=1)
        while not self.is_scheduled_session(current):
            current -= timedelta(days=1)
        return current

    def latest_session_on_or_before(self, day: date) -> date:
        day = self._check(day)
        return day if self.is_scheduled_session(day) else self.previous_session(day)

    def sessions_in(self, start: date, end: date) -> list[date]:
        """Scheduled sessions in the closed interval [start, end]."""
        return list(self._iter(self._check(start), self._check(end)))

    def sessions_between(self, after: date, through: date) -> list[date]:
        """Scheduled sessions in the half-open interval (after, through].

        This is the shape ingestion needs: sessions after the last committed one, up to and
        including the as-of session (ENGINEERING.md 9.2 step 3).
        """
        after, through = self._check(after), self._check(through)
        if through <= after:
            return []
        return list(self._iter(after + timedelta(days=1), through))

    def _iter(self, start: date, end: date) -> Iterator[date]:
        current = start
        while current <= end:
            if self.is_scheduled_session(current):
                yield current
            current += timedelta(days=1)


def reconcile(
    calendar: TradingCalendar,
    traded_dates: set[date],
    start: date,
    end: date,
    *,
    ignore: tuple[tuple[date, date], ...] = (),
) -> tuple[list[date], list[date]]:
    """Compare the calendar with dates on which trading data exists.

    Returns (scheduled sessions with no data, dates with data that the calendar closes).
    ``ignore`` lists known whole-period data gaps to leave out of the first list.
    """

    def ignored(day: date) -> bool:
        return any(lo <= day <= hi for lo, hi in ignore)

    no_data = [
        d for d in calendar.sessions_in(start, end) if d not in traded_dates and not ignored(d)
    ]
    closed_with_data = sorted(
        d
        for d in traded_dates
        if start <= d <= end and (d.weekday() >= SATURDAY or not calendar.is_scheduled_session(d))
    )
    return no_data, closed_with_data
