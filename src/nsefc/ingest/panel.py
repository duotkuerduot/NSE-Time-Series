"""Panel rules: classify sessions from observed rows first, then synthesise.

1. A security is listed from its first to its last appearance in the data.
2. Market-level checks run first, on observed rows only: a scheduled session with no rows for
   any security is a *missing* session, not a holiday.
3. Only then does a listed security with no row in a *held* session get a carried-forward row
   (volume 0, close = last close).
4. Nothing is synthesised inside a missing session; missing sessions are never filled.
"""

from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from nsefc.calendar import CalendarCoverageError, TradingCalendar


def classify_sessions(
    observed: pd.Series,
    calendar: TradingCalendar,
    first: pd.Timestamp,
    last: pd.Timestamp,
) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    """Every weekday in [first, last] as held, missing or holiday.

    ``observed`` counts securities with a source row per date. Returns the sessions frame and
    the dates with data that the calendar closes (DAT-02; for history, the data wins).
    """
    counts = observed.to_dict()
    records = []
    off_calendar: list[pd.Timestamp] = []
    day = first.date()
    end = last.date()
    while day <= end:
        if day.weekday() < 5:
            stamp = pd.Timestamp(day)
            n = int(counts.get(stamp, 0))
            try:
                scheduled = calendar.is_scheduled_session(day)
                holiday = calendar.holiday_on(day)
                reason = holiday.name if holiday else ""
            except CalendarCoverageError:
                scheduled, reason = n > 0, "outside calendar coverage"
            if n > 0:
                status = "held"
                if not scheduled:
                    off_calendar.append(stamp)
            elif scheduled:
                status, reason = "missing", "no data for any security"
            else:
                status = "holiday"
            records.append(
                {"session_date": stamp, "status": status, "n_securities": n, "reason": reason}
            )
        day += timedelta(days=1)
    frame = pd.DataFrame.from_records(records)
    return frame, off_calendar


def synthesise(rows: pd.DataFrame, held: pd.DatetimeIndex) -> pd.DataFrame:
    """Add carried-forward rows for listed securities absent from a held session."""
    pieces = []
    held = held.sort_values()
    for ticker, group in rows.groupby("ticker", sort=True):
        group = group.sort_values("session_date").set_index("session_date")
        span = held[(held >= group.index[0]) & (held <= group.index[-1])]
        full = group.reindex(span)
        synthetic = full["close"].isna()
        if synthetic.any():
            for column in ("close", "source", "source_file_sha256"):
                full[column] = full[column].ffill()
            full.loc[synthetic, "volume"] = 0
            for column in ("prev_close_reported", "open", "high", "low", "turnover"):
                full.loc[synthetic, column] = np.nan
        full["is_carried_forward"] = synthetic.to_numpy()
        full["ticker"] = ticker
        pieces.append(full.reset_index(names="session_date"))
    out = pd.concat(pieces, ignore_index=True)
    out["volume"] = out["volume"].astype("int64")
    out["traded"] = out["volume"] > 0
    return out
