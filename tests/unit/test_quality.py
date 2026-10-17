"""Every quality check in §6.6 has a passing and a failing case (§16.1)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nsefc.domain import Severity
from nsefc.quality.checks import (
    dat01,
    dat02,
    dat03,
    gap01,
    key01,
    missing_ranges,
    mkt01,
    prc01,
    sch02,
    vol01,
)


def rows(**columns: list[object]) -> pd.DataFrame:
    base = {
        "ticker": ["AAA", "BBB"],
        "code": ["AAA", "BBB"],
        "session_date": pd.to_datetime(["2025-01-02", "2025-01-02"]),
        "close": [10.0, 20.0],
        "high": [10.5, 20.5],
        "low": [9.5, 19.5],
        "volume": [100.0, 200.0],
        "source_file": ["f.csv", "f.csv"],
        "line": [2, 3],
    }
    base.update(columns)  # type: ignore[arg-type]
    frame = pd.DataFrame(base)
    frame["session_date"] = pd.to_datetime(frame["session_date"])
    return frame


def test_sch02_passes_and_excludes() -> None:
    bad, result = sch02(rows())
    assert result.count == 0 and not bad.any()
    bad, result = sch02(rows(close=[0.0, 20.0], high=[10.5, 19.0], low=[9.5, 19.5]))
    assert result.severity is Severity.EXCLUDE
    assert bad.tolist() == [True, True]  # zero price; high below low
    assert sch02(rows(volume=[-1.0, 1.0]))[0].tolist() == [True, False]


def test_key01() -> None:
    assert key01(rows()).count == 0
    dup = rows(ticker=["AAA", "AAA"])
    result = key01(dup)
    assert (
        result.count == 1
        and result.severity is Severity.ERROR
        and "corrections.yaml" in result.note
    )


def test_dat01() -> None:
    assert dat01(rows()).count == 0
    weekend = rows(session_date=["2025-01-04", "2025-01-02"])  # a Saturday
    assert dat01(weekend).count == 1


def test_dat03() -> None:
    assert dat03(rows(), {"f.csv": 2025}).count == 0
    assert dat03(rows(), {"f.csv": 2024}).count == 2
    assert dat03(rows(), {"f.csv": None}).count == 0  # imports state no year


def test_dat02_lists_off_calendar_days() -> None:
    assert dat02([]).count == 0
    result = dat02([pd.Timestamp("2010-12-27")])
    assert (
        result.count == 1 and result.severity is Severity.WARN and result.examples == ["2010-12-27"]
    )


def bars(
    closes: list[float], volume: list[float] | None = None, turnover: list[float] | None = None
) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame(
        {
            "ticker": ["AAA"] * n,
            "session_date": pd.bdate_range("2025-01-06", periods=n),
            "close": closes,
            "volume": volume or [100.0] * n,
            "turnover": turnover or [np.nan] * n,
        }
    )


def test_prc01_marks_moves_beyond_the_band_plus_margin() -> None:
    events, result = prc01(bars([10.0, 11.0, 11.0]), 0.105)
    assert result.count == 0 and not events.any()  # exactly +10% is inside
    events, result = prc01(bars([10.0, 11.06, 5.0]), 0.105)
    assert events.tolist() == [False, True, True] and result.severity is Severity.EXCLUDE


def test_vol01() -> None:
    assert "Not applicable" in vol01(bars([10.0, 10.0]), 0.02).note
    consistent = bars([10.0, 10.0], volume=[100, 100], turnover=[1000.0, 1001.0])
    assert vol01(consistent, 0.02).count == 0
    off = bars([10.0, 10.0], volume=[100, 100], turnover=[1000.0, 1500.0])
    assert vol01(off, 0.02).count == 1


def sessions(counts: list[int], statuses: list[str] | None = None) -> pd.DataFrame:
    n = len(counts)
    return pd.DataFrame(
        {
            "session_date": pd.bdate_range("2025-01-06", periods=n),
            "status": statuses or ["held"] * n,
            "n_securities": counts,
        }
    )


def test_mkt01_flags_thin_sessions_against_the_trailing_median() -> None:
    thin, result = mkt01(sessions([60] * 25), 20, 0.7)
    assert result.count == 0 and not thin.any()
    thin, result = mkt01(sessions([60] * 24 + [20]), 20, 0.7)
    assert result.count == 1 and bool(thin.iloc[-1]) and result.severity is Severity.WARN


def test_gap01_and_missing_ranges() -> None:
    assert gap01(sessions([5, 5, 5])).count == 0
    frame = sessions(
        [5, 0, 0, 0, 5, 0, 5], ["held", "missing", "holiday", "missing", "held", "missing", "held"]
    )
    result = gap01(frame)
    assert result.count == 3
    # A holiday inside a run of missing sessions does not split it.
    assert missing_ranges(frame) == [
        ("2025-01-07", "2025-01-09", 2),
        ("2025-01-13", "2025-01-13", 1),
    ]


@pytest.mark.parametrize("check", [sch02, key01, dat01])
def test_every_check_reports_examples(check) -> None:  # type: ignore[no-untyped-def]
    frame = rows(
        ticker=["AAA", "AAA"], close=[0.0, 20.0], session_date=["2025-01-04", "2025-01-04"]
    )
    result = check(frame)
    result = result[1] if isinstance(result, tuple) else result
    assert result.count > 0 and result.examples
