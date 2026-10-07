from __future__ import annotations

from datetime import date, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from nsefc.calendar import load_calendar
from tests.conftest import ROOT

CALENDAR = load_calendar(ROOT / "config" / "calendar" / "nse_holidays.yaml")
days = st.dates(min_value=date(2005, 1, 10), max_value=date(2026, 12, 20))


@settings(max_examples=300, deadline=None)
@given(days)
def test_next_session_is_the_first_session_after(day: date) -> None:
    nxt = CALENDAR.next_session(day)
    assert nxt > day and CALENDAR.is_scheduled_session(nxt)
    between = day + timedelta(days=1)
    while between < nxt:
        assert not CALENDAR.is_scheduled_session(between)
        between += timedelta(days=1)


@settings(max_examples=300, deadline=None)
@given(days)
def test_previous_and_next_are_inverse_on_sessions(day: date) -> None:
    session = CALENDAR.latest_session_on_or_before(day)
    assert CALENDAR.previous_session(CALENDAR.next_session(session)) == session
    assert CALENDAR.next_session(CALENDAR.previous_session(session)) == session


@settings(max_examples=150, deadline=None)
@given(days, st.integers(min_value=0, max_value=40))
def test_sessions_between_matches_stepping(day: date, span: int) -> None:
    end = min(day + timedelta(days=span), date(2026, 12, 20))
    stepped, current = [], day
    while True:
        current = CALENDAR.next_session(current)
        if current > end:
            break
        stepped.append(current)
    assert CALENDAR.sessions_between(day, end) == stepped
