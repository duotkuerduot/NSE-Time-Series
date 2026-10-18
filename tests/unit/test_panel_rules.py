"""Panel rules: classify from observed rows first, then synthesise held sessions only."""

from __future__ import annotations

import pandas as pd

from nsefc.calendar import TradingCalendar
from nsefc.ingest.panel import classify_sessions, synthesise


def test_classification_from_observed_rows(calendar: TradingCalendar) -> None:
    observed = pd.Series(
        {
            pd.Timestamp("2025-04-16"): 60,  # Wed
            pd.Timestamp("2025-04-17"): 61,  # Thu
            # Fri 18 Apr 2025 is Good Friday, Mon 21 Apr Easter Monday: holidays
            # Tue 22 Apr: scheduled, no rows -> missing
            pd.Timestamp("2025-04-23"): 60,
        }
    )
    frame, off = classify_sessions(
        observed, calendar, pd.Timestamp("2025-04-16"), pd.Timestamp("2025-04-23")
    )
    status = dict(zip(frame["session_date"].dt.date.astype(str), frame["status"], strict=True))
    assert status == {
        "2025-04-16": "held",
        "2025-04-17": "held",
        "2025-04-18": "holiday",
        "2025-04-21": "holiday",
        "2025-04-22": "missing",
        "2025-04-23": "held",
    }
    assert off == []


def test_data_on_a_holiday_is_kept_and_listed(calendar: TradingCalendar) -> None:
    observed = pd.Series({pd.Timestamp("2025-04-17"): 60, pd.Timestamp("2025-04-18"): 3})
    frame, off = classify_sessions(
        observed, calendar, pd.Timestamp("2025-04-17"), pd.Timestamp("2025-04-18")
    )
    assert frame["status"].tolist() == ["held", "held"]
    assert off == [pd.Timestamp("2025-04-18")]  # DAT-02 lists it for review


def test_synthesis_fills_held_sessions_only_inside_the_listing_span() -> None:
    held = pd.DatetimeIndex(
        pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-07", "2025-01-08", "2025-01-09"])
    )
    # 6 Jan is a missing session: it is not in `held`, so nothing is synthesised for it.
    rows = pd.DataFrame(
        {
            "ticker": ["A", "A", "A", "B"],
            "session_date": pd.to_datetime(
                ["2025-01-02", "2025-01-07", "2025-01-08", "2025-01-08"]
            ),
            "close": [10.0, 11.0, 12.0, 5.0],
            "prev_close_reported": [9.0, 10.0, 11.0, 5.0],
            "open": [float("nan")] * 4,
            "high": [10.0, 11.0, 12.0, 5.0],
            "low": [10.0, 11.0, 12.0, 5.0],
            "volume": [100, 100, 100, 50],
            "turnover": [float("nan")] * 4,
            "source": ["s"] * 4,
            "source_file_sha256": ["h"] * 4,
        }
    )
    out = synthesise(rows, held).set_index(["ticker", "session_date"])
    a = out.loc["A"]
    assert a.index.strftime("%m-%d").tolist() == [
        "01-02",
        "01-03",
        "01-07",
        "01-08",
    ]  # listed until 8 Jan
    carried = a.loc[pd.Timestamp("2025-01-03")]
    assert carried["is_carried_forward"] and carried["close"] == 10.0 and carried["volume"] == 0
    assert not carried["traded"] and pd.isna(carried["high"])
    assert out.loc["B"].index.tolist() == [
        pd.Timestamp("2025-01-08")
    ]  # B listed from its first row
    assert not out["is_carried_forward"].loc[("A", pd.Timestamp("2025-01-08"))]
