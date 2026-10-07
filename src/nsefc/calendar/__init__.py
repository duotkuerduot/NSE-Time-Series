"""NSE trading calendar and session arithmetic.

Every other module uses ``is_scheduled_session``, ``next_session``, ``previous_session`` and
``sessions_between``; nobody computes "tomorrow" with date arithmetic (ENGINEERING.md 7.5).
"""

from pathlib import Path

from nsefc.calendar.core import (
    CalendarCoverageError,
    CalendarError,
    CalendarSpec,
    Holiday,
    HolidayKind,
    TradingCalendar,
    easter_sunday,
    reconcile,
)


def load_calendar(path: Path | str = Path("config/calendar/nse_holidays.yaml")) -> TradingCalendar:
    return TradingCalendar.from_yaml(Path(path))


__all__ = [
    "CalendarCoverageError",
    "CalendarError",
    "CalendarSpec",
    "Holiday",
    "HolidayKind",
    "TradingCalendar",
    "easter_sunday",
    "load_calendar",
    "reconcile",
]
