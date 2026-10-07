from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
import yaml

from nsefc.calendar import (
    CalendarCoverageError,
    CalendarError,
    TradingCalendar,
    easter_sunday,
    reconcile,
)


def closures(calendar: TradingCalendar, year: int, until: date | None = None) -> set[str]:
    return {
        h.date.strftime("%m%d") for h in calendar.holidays(year) if until is None or h.date <= until
    }


# Weekdays without trading in the repository's NSE data (see reports/calendar-reconciliation.md).
TRADING_DATA_CLOSURES_2024 = {
    "0101",
    "0329",
    "0401",
    "0410",
    "0501",
    "0510",
    "0617",
    "1010",
    "1021",
    "1101",
    "1212",
    "1225",
    "1226",
}
TRADING_DATA_CLOSURES_2025_JAN_OCT = {
    "0101",
    "0331",
    "0418",
    "0421",
    "0501",
    "0602",
    "0606",
    "1010",
    "1017",
    "1020",
}


def test_2024_matches_trading_data(calendar: TradingCalendar) -> None:
    assert closures(calendar, 2024) == TRADING_DATA_CLOSURES_2024


def test_2025_matches_trading_data(calendar: TradingCalendar) -> None:
    assert closures(calendar, 2025, until=date(2025, 10, 31)) == TRADING_DATA_CLOSURES_2025_JAN_OCT
    assert closures(calendar, 2025) - TRADING_DATA_CLOSURES_2025_JAN_OCT == {"1212", "1225", "1226"}


def test_2026_known_holidays(calendar: TradingCalendar) -> None:
    # Mazingira Day (10 Oct), Jamhuri Day (12 Dec) and Boxing Day fall on Saturdays in 2026.
    assert closures(calendar, 2026) == {
        "0101",
        "0320",
        "0403",
        "0406",
        "0501",
        "0527",
        "0601",
        "1020",
        "1225",
    }
    names = {h.date: h.name for h in calendar.holidays(2026, weekdays_only=False)}
    assert names[date(2026, 10, 10)] == "Mazingira Day"
    assert names[date(2026, 5, 27)] == "Idd-ul-Azha"


def test_engineering_md_mashujaa_example(calendar: TradingCalendar) -> None:
    # ENGINEERING.md 7.5: the forecast made after Mon 19 Oct 2026 targets Wed 21 Oct.
    assert calendar.next_session(date(2026, 10, 19)) == date(2026, 10, 21)
    assert calendar.previous_session(date(2026, 10, 21)) == date(2026, 10, 19)
    assert not calendar.is_scheduled_session(date(2026, 10, 20))


@pytest.mark.parametrize(
    ("year", "closed"),
    [
        (2016, {"1226", "1227"}),  # Christmas on Sunday, Boxing Day on Monday -> 26 and 27
        (2022, {"1226", "1227"}),
        (2021, {"1227"}),  # Christmas on Saturday stays; Boxing Day Sunday -> Monday
    ],
)
def test_sunday_rule_cascades(calendar: TradingCalendar, year: int, closed: set[str]) -> None:
    december = {d for d in closures(calendar, year) if d.startswith("12") and d > "1224"}
    assert december == closed


def test_new_year_on_sunday_observed_monday(calendar: TradingCalendar) -> None:
    holiday = calendar.holiday_on(date(2023, 1, 2))
    assert holiday is not None and holiday.observed_for == date(2023, 1, 1)


@pytest.mark.parametrize(
    ("year", "sunday"),
    [
        (2008, date(2008, 3, 23)),
        (2019, date(2019, 4, 21)),
        (2024, date(2024, 3, 31)),
        (2025, date(2025, 4, 20)),
        (2026, date(2026, 4, 5)),
    ],
)
def test_easter(year: int, sunday: date) -> None:
    assert easter_sunday(year) == sunday


def test_moi_day_history(calendar: TradingCalendar) -> None:
    assert calendar.holiday_on(date(2008, 10, 10)) is not None
    assert calendar.is_scheduled_session(date(2012, 10, 10))  # not observed 2010-2017
    assert calendar.holiday_on(date(2018, 10, 10)) is not None


def test_weekends_are_never_sessions(calendar: TradingCalendar) -> None:
    assert not calendar.is_scheduled_session(date(2026, 10, 10))  # Saturday
    assert not calendar.is_scheduled_session(date(2026, 10, 11))  # Sunday


def test_sessions_between_is_half_open(calendar: TradingCalendar) -> None:
    sessions = calendar.sessions_between(date(2026, 10, 16), date(2026, 10, 21))
    assert sessions == [date(2026, 10, 19), date(2026, 10, 21)]
    assert calendar.sessions_between(date(2026, 10, 21), date(2026, 10, 21)) == []
    assert calendar.sessions_in(date(2026, 10, 16), date(2026, 10, 16)) == [date(2026, 10, 16)]


def test_latest_session_on_or_before(calendar: TradingCalendar) -> None:
    assert calendar.latest_session_on_or_before(date(2026, 10, 11)) == date(2026, 10, 9)
    assert calendar.latest_session_on_or_before(date(2026, 10, 9)) == date(2026, 10, 9)


def test_2026_session_count_to_date(calendar: TradingCalendar) -> None:
    # The gap the review flagged (MF-2): 1 Jan to 7 Oct 2026.
    assert len(calendar.sessions_in(date(2026, 1, 1), date(2026, 10, 7))) == 193


def test_coverage_is_enforced(calendar: TradingCalendar) -> None:
    with pytest.raises(CalendarCoverageError):
        calendar.is_scheduled_session(date(2027, 1, 4))
    with pytest.raises(CalendarCoverageError):
        calendar.next_session(date(2026, 12, 31))
    assert calendar.days_of_coverage_left(date(2026, 10, 7)) == 85


def test_timestamps_are_rejected(calendar: TradingCalendar) -> None:
    with pytest.raises(TypeError):
        calendar.is_scheduled_session(datetime(2026, 10, 7, 12, 0))  # type: ignore[arg-type]


def test_reconcile_reports_both_directions(calendar: TradingCalendar) -> None:
    sessions = set(calendar.sessions_in(date(2026, 10, 1), date(2026, 10, 9)))
    traded = (sessions - {date(2026, 10, 6)}) | {date(2026, 10, 10)}
    no_data, closed_with_data = reconcile(calendar, traded, date(2026, 10, 1), date(2026, 10, 9))
    assert no_data == [date(2026, 10, 6)]
    assert closed_with_data == []
    _, conflicts = reconcile(calendar, traded, date(2026, 10, 1), date(2026, 10, 12))
    assert conflicts == [date(2026, 10, 10)]


def test_bad_spec_is_rejected(tmp_path: Path, repo_root: Path) -> None:
    spec = yaml.safe_load((repo_root / "config/calendar/nse_holidays.yaml").read_text())
    spec["closures"].append(
        {
            "date": date(2025, 10, 18),
            "name": "Saturday closure",
            "status": "confirmed",
            "source": "test",
        }
    )
    path = tmp_path / "cal.yaml"
    path.write_text(yaml.safe_dump(spec))
    with pytest.raises(CalendarError, match="weekend"):
        TradingCalendar.from_yaml(path)


def test_held_sessions_override_the_sunday_rule(calendar: TradingCalendar) -> None:
    # The data shows full sessions on these days, so history follows the data (7.5).
    assert calendar.is_scheduled_session(date(2010, 12, 27))
    assert calendar.is_scheduled_session(date(2011, 12, 27))
    assert not calendar.is_scheduled_session(date(2011, 12, 26))  # Boxing Day itself
    # The cascade still holds where the data shows it.
    assert not calendar.is_scheduled_session(date(2016, 12, 27))
    assert not calendar.is_scheduled_session(date(2022, 12, 27))


@pytest.mark.parametrize(
    ("held", "message"),
    [
        ({"date": "2010-12-25", "status": "confirmed", "source": "x"}, "weekend"),
        ({"date": "2022-08-09", "status": "confirmed", "source": "x"}, "both"),
    ],
)
def test_held_session_validation(
    repo_root: Path, tmp_path: Path, held: dict[str, str], message: str
) -> None:
    spec = yaml.safe_load((repo_root / "config/calendar/nse_holidays.yaml").read_text())
    spec["held_sessions"] = [held]
    path = tmp_path / "calendar.yaml"
    path.write_text(yaml.safe_dump(spec))
    with pytest.raises(CalendarError, match=message):
        TradingCalendar.from_yaml(path)
