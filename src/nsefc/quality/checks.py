"""Data-quality checks (§6.6).

Severity ``error`` blocks the run (exit code 20), ``exclude`` drops rows from modelling (they
stay in the display data) and ``warn`` is reported only. Every result carries a count and a
few examples, and all of them are written to ``data/reports/data-audit.md``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from nsefc.domain import Severity

EXAMPLES = 12


class DataQualityError(RuntimeError):
    """An error-severity check failed (exit code 20)."""

    def __init__(self, results: list[CheckResult]) -> None:
        self.results = results
        lines = [
            f"{r.id} {r.title}: {r.count} problem(s); e.g. {', '.join(r.examples[:3])}"
            for r in results
        ]
        super().__init__("data-quality check failed:\n  " + "\n  ".join(lines))


@dataclass(slots=True)
class CheckResult:
    id: str
    title: str
    severity: Severity
    count: int = 0
    examples: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def failed(self) -> bool:
        return self.count > 0

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity.value,
            "count": self.count,
            "examples": self.examples,
            "note": self.note,
        }


def _examples(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    out = []
    for _, row in frame.head(EXAMPLES).iterrows():
        parts = []
        for column in columns:
            value = row[column]
            if isinstance(value, pd.Timestamp):
                value = value.date().isoformat()
            parts.append(str(value))
        out.append(" ".join(parts))
    return out


def sch02(rows: pd.DataFrame) -> tuple[pd.Series, CheckResult]:
    """SCH-02: close > 0, volume >= 0, high >= low where present. Bad rows are excluded."""
    bad = (
        ~(rows["close"] > 0)
        | (rows["volume"] < 0)
        | (rows["high"].notna() & rows["low"].notna() & (rows["high"] < rows["low"]))
    )
    result = CheckResult(
        "SCH-02", "Positive price, non-negative volume, high >= low", Severity.EXCLUDE
    )
    result.count = int(bad.sum())
    result.examples = _examples(rows[bad], ["source_file", "line", "code", "session_date"])
    return bad, result


def key01(rows: pd.DataFrame) -> CheckResult:
    """KEY-01: one row per (ticker, session_date) after corrections and duplicate removal."""
    dup = rows.duplicated(["ticker", "session_date"], keep=False)
    result = CheckResult(
        "KEY-01", "No duplicate (ticker, session) after corrections", Severity.ERROR
    )
    keys = rows.loc[dup, ["ticker", "session_date", "source_file", "line"]]
    result.count = int(rows[dup].groupby(["ticker", "session_date"]).ngroups)
    result.examples = _examples(keys, ["ticker", "session_date", "source_file", "line"])
    if result.count:
        result.note = "Add a reviewed rule to reference/corrections.yaml for each conflicting pair."
    return result


def dat01(rows: pd.DataFrame) -> CheckResult:
    """DAT-01: every date is a weekday (a misdated block shows up here unless corrected)."""
    weekend = rows["session_date"].dt.dayofweek >= 5
    result = CheckResult("DAT-01", "Every date is a weekday", Severity.ERROR)
    groups = rows[weekend].groupby(["source_file", "session_date"]).size().reset_index(name="rows")
    result.count = int(weekend.sum())
    result.examples = _examples(groups, ["source_file", "session_date", "rows"])
    if result.count:
        result.note = (
            "Fix with a `redate` rule in reference/corrections.yaml keyed to the file's SHA-256."
        )
    return result


def dat03(rows: pd.DataFrame, file_years: dict[str, int | None]) -> CheckResult:
    """DAT-03: a file's rows fall in the year its name states (catches misdated rows)."""
    expected = rows["source_file"].map(file_years)
    wrong = expected.notna() & (rows["session_date"].dt.year != expected)
    result = CheckResult("DAT-03", "Dates fall within the year each file covers", Severity.ERROR)
    groups = rows[wrong].groupby(["source_file", "session_date"]).size().reset_index(name="rows")
    result.count = int(wrong.sum())
    result.examples = _examples(groups, ["source_file", "session_date", "rows"])
    return result


def dat02(off_calendar: list[pd.Timestamp]) -> CheckResult:
    """DAT-02: data on a day the calendar closes (data wins for history; listed for review)."""
    result = CheckResult("DAT-02", "Data only on scheduled or held sessions", Severity.WARN)
    result.count = len(off_calendar)
    result.examples = [d.date().isoformat() for d in off_calendar[:EXAMPLES]]
    return result


def prc01(bars: pd.DataFrame, threshold: float) -> tuple[pd.Series, CheckResult]:
    """PRC-01: an absolute move beyond the band (+0.5 pp) is an event (§6.7)."""
    ordered = bars.sort_values(["ticker", "session_date"])
    previous = ordered.groupby("ticker")["close"].shift(1)
    change = ordered["close"] / previous - 1
    events = (change.abs() > threshold + 1e-12).reindex(bars.index).fillna(False).astype(bool)
    result = CheckResult(
        "PRC-01",
        f"Daily move within ±{threshold:.1%} (else an event, excluded from modelling)",
        Severity.EXCLUDE,
    )
    result.count = int(events.sum())
    listed = bars[events].assign(
        change=change.reindex(bars.index)[events].map(lambda v: f"{v:+.1%}")
    )
    result.examples = _examples(
        listed.sort_values("session_date"), ["ticker", "session_date", "change"]
    )
    return events, result


def vol01(bars: pd.DataFrame, tolerance: float) -> CheckResult:
    """VOL-01: turnover / volume is close to the VWAP close where all are present."""
    result = CheckResult(
        "VOL-01", "Turnover / volume close to the close (VWAP basis)", Severity.WARN
    )
    present = bars["turnover"].notna() & (bars["volume"] > 0)
    if not present.any():
        result.note = "Not applicable: the dataset has no turnover column."
        return result
    implied = bars.loc[present, "turnover"] / bars.loc[present, "volume"]
    off = (implied / bars.loc[present, "close"] - 1).abs() > tolerance
    result.count = int(off.sum())
    result.examples = _examples(bars.loc[present][off.to_numpy()], ["ticker", "session_date"])
    return result


def mkt01(sessions: pd.DataFrame, window: int, min_share: float) -> tuple[pd.Series, CheckResult]:
    """MKT-01: a held session quotes at least 70% of the trailing 20-session median count."""
    held = sessions["status"] == "held"
    counts = sessions.loc[held, "n_securities"].astype(float)
    baseline = counts.shift(1).rolling(window, min_periods=max(5, window // 2)).median()
    thin = (counts < min_share * baseline).reindex(sessions.index).fillna(False).astype(bool)
    result = CheckResult(
        "MKT-01",
        f"Securities quoted per session >= {min_share:.0%} of the trailing median",
        Severity.WARN,
    )
    result.count = int(thin.sum())
    result.examples = [
        f"{d.date().isoformat()} ({int(n)} securities)"
        for d, n in zip(
            sessions.loc[thin, "session_date"], sessions.loc[thin, "n_securities"], strict=True
        )
    ][:EXAMPLES]
    if result.count:
        result.note = "Market-context features are null for these sessions."
    return thin, result


def gap01(sessions: pd.DataFrame) -> CheckResult:
    """GAP-01: list missing sessions as ranges."""
    missing = sessions.loc[sessions["status"] == "missing", "session_date"].reset_index(drop=True)
    result = CheckResult(
        "GAP-01", "Missing sessions (scheduled, no data for any security)", Severity.WARN
    )
    result.count = len(missing)
    result.examples = [
        f"{a} to {b} ({n} sessions)" if n > 1 else f"{a}" for a, b, n in missing_ranges(sessions)
    ][: EXAMPLES * 3]
    return result


def missing_ranges(sessions: pd.DataFrame) -> list[tuple[str, str, int]]:
    """Consecutive runs of missing sessions (holidays between them do not break a run)."""
    ordered = sessions[sessions["status"] != "holiday"].reset_index(drop=True)
    runs: list[tuple[str, str, int]] = []
    start = None
    count = 0
    previous = None
    for day, status in zip(ordered["session_date"], ordered["status"], strict=True):
        if status == "missing":
            if start is None:
                start, count = day, 0
            count += 1
            previous = day
        elif start is not None and previous is not None:
            runs.append((start.date().isoformat(), previous.date().isoformat(), count))
            start = None
    if start is not None and previous is not None:
        runs.append((start.date().isoformat(), previous.date().isoformat(), count))
    return runs


def errors(results: list[CheckResult]) -> list[CheckResult]:
    return [r for r in results if r.severity is Severity.ERROR and r.failed]


def as_float(values: pd.Series) -> np.ndarray:
    return values.to_numpy(dtype=float)
