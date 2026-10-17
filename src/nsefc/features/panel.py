"""The only door into the data for feature code (leakage rule L1, §8.3).

``load_panel(..., as_of=T)`` keeps rows with ``session_date <= T`` and asserts it, so a
feature can only ever see the past. ``Panel`` also carries the per-row bookkeeping that the
rolling features and the gap guard need: each row's position within its security and the
number of missing sessions before it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from nsefc.calendar import TradingCalendar


class LeakageError(AssertionError):
    """Data from after the as-of session reached feature code."""


@dataclass(frozen=True)
class Panel:
    as_of: pd.Timestamp
    bars: pd.DataFrame  # sorted by (ticker, session_date); one row per held session listed
    sessions: pd.DataFrame  # every weekday up to as_of: held, missing or holiday
    indices: pd.DataFrame  # index levels (index, session_date, level)
    securities: pd.DataFrame  # ticker, name, sector, instrument_type, ...
    calendar: TradingCalendar

    @property
    def held(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(
            self.sessions.loc[self.sessions["status"] == "held", "session_date"]
        )

    def assert_as_of(self) -> None:
        for name in ("bars", "sessions", "indices"):
            frame: pd.DataFrame = getattr(self, name)
            if len(frame) and frame["session_date"].max() > self.as_of:
                raise LeakageError(f"{name} contains rows after {self.as_of.date()}")


def load_panel(
    *,
    bars: pd.DataFrame,
    sessions: pd.DataFrame,
    indices: pd.DataFrame,
    securities: pd.DataFrame,
    calendar: TradingCalendar,
    as_of: pd.Timestamp | None = None,
) -> Panel:
    """Truncate everything at ``as_of`` (default: the last held session) and add bookkeeping."""
    held = sessions.loc[sessions["status"] == "held", "session_date"]
    as_of = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp(held.max())
    keep_bars = bars[bars["session_date"] <= as_of]
    keep_sessions = sessions[sessions["session_date"] <= as_of].reset_index(drop=True)
    keep_indices = indices[indices["session_date"] <= as_of]

    bars_sorted = keep_bars.sort_values(["ticker", "session_date"], kind="stable").reset_index(
        drop=True
    )
    held_sorted = keep_sessions.loc[keep_sessions["status"] == "held", "session_date"].sort_values()
    is_missing = (keep_sessions["status"] == "missing").to_numpy()
    cum_missing_all = np.cumsum(is_missing)  # missing sessions on or before each weekday
    missing_before = pd.Series(cum_missing_all, index=keep_sessions["session_date"])
    held_index = pd.Series(np.arange(len(held_sorted)), index=held_sorted.to_numpy())
    dates = bars_sorted["session_date"]
    bars_sorted["held_k"] = held_index.reindex(dates.to_numpy()).to_numpy()
    bars_sorted["missing_before"] = missing_before.reindex(dates.to_numpy()).to_numpy()
    bars_sorted["pos"] = bars_sorted.groupby("ticker", sort=False).cumcount()
    panel = Panel(
        as_of=as_of,
        bars=bars_sorted,
        sessions=keep_sessions,
        indices=keep_indices.reset_index(drop=True),
        securities=securities.reset_index(drop=True),
        calendar=calendar,
    )
    panel.assert_as_of()
    return panel
