"""Shared fixtures (ENGINEERING.md §16).

Synthetic panels are built in memory for the ML and leakage tests; the pipeline tests run the
real stages on the synthetic sample dataset (§16.3) in a temporary data folder.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from nsefc.calendar import TradingCalendar, load_calendar
from nsefc.config import Settings, load_settings
from nsefc.features import Panel, load_panel

ROOT = Path(__file__).resolve().parents[1]
CALENDAR_FILE = ROOT / "config" / "calendar" / "nse_holidays.yaml"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def calendar() -> TradingCalendar:
    return load_calendar(CALENDAR_FILE)


def settings_for(data_dir: Path, profile: str = "test", **overrides: Any) -> Settings:
    """Settings for a temporary data folder; environment variables are ignored."""
    return load_settings(
        profile,  # type: ignore[arg-type]
        project_root=ROOT,
        overrides={"paths.data_dir": str(data_dir), **overrides},
        environ={},
    )


# ---------------------------------------------------------------- synthetic panels
@dataclass
class SyntheticMarket:
    """Inputs for ``load_panel``: one ordinary share per ticker, every session held."""

    bars: pd.DataFrame
    sessions: pd.DataFrame
    indices: pd.DataFrame
    securities: pd.DataFrame
    calendar: TradingCalendar

    def panel(self, as_of: pd.Timestamp | None = None) -> Panel:
        return load_panel(
            bars=self.bars,
            sessions=self.sessions,
            indices=self.indices,
            securities=self.securities,
            calendar=self.calendar,
            as_of=as_of,
        )


def synthetic_market(
    calendar: TradingCalendar,
    *,
    tickers: int = 4,
    start: date = date(2015, 1, 2),
    sessions: int = 300,
    phi: float = 0.0,
    sigma: float = 0.015,
    seed: int = 7,
    trade_probability: float = 1.0,
    missing: tuple[int, ...] = (),
    events: tuple[tuple[int, int], ...] = (),
) -> SyntheticMarket:
    """Log prices following AR(1) returns ``r_t = phi r_{t-1} + e_t``.

    ``missing`` lists session numbers with no data at all (missing sessions); ``events`` lists
    (ticker number, session number) pairs whose close jumps by 30% (a PRC-01 event).
    """
    rng = np.random.default_rng(seed)
    days = calendar.sessions_in(start, calendar.coverage_end)[:sessions]
    assert len(days) == sessions, "the calendar does not cover that many sessions"
    missing_days = {days[i] for i in missing}
    rows = []
    for t in range(tickers):
        price = 20.0 + 10 * t
        r_prev = 0.0
        for i, day in enumerate(days):
            if day in missing_days:
                continue
            r = phi * r_prev + rng.normal(0.0, sigma)
            r_prev = r
            price = price * float(np.exp(r))
            if (t, i) in events:
                price *= 1.3
            traded = bool(rng.random() < trade_probability) or i == 0
            volume = int(rng.integers(50_000, 200_000)) if traded else 0
            rows.append(
                {
                    "ticker": f"T{t:02d}",
                    "session_date": pd.Timestamp(day),
                    "close": round(price, 6),
                    "high": price * 1.01 if traded else np.nan,
                    "low": price * 0.99 if traded else np.nan,
                    "volume": volume,
                    "traded": traded,
                    "turnover": np.nan,
                    "is_event": (t, i) in events,
                    "is_carried_forward": False,
                }
            )
    bars = pd.DataFrame(rows)
    status = ["missing" if d in missing_days else "held" for d in days]
    sessions_frame = pd.DataFrame(
        {
            "session_date": pd.to_datetime(days),
            "status": status,
            "n_securities": [0 if s == "missing" else tickers for s in status],
            "reason": "",
            "market_ok": True,
        }
    )
    indices = pd.DataFrame(
        {
            "session_date": pd.Series(dtype="datetime64[ns]"),
            "index": pd.Series(dtype=str),
            "level": pd.Series(dtype=float),
        }
    )
    securities = pd.DataFrame(
        {
            "ticker": [f"T{t:02d}" for t in range(tickers)],
            "name": [f"Test {t:02d}" for t in range(tickers)],
            "sector": ["Banking" if t % 2 else "Energy" for t in range(tickers)],
            "instrument_type": "ordinary",
        }
    )
    return SyntheticMarket(bars, sessions_frame, indices, securities, calendar)


@pytest.fixture
def make_market(calendar: TradingCalendar) -> Callable[..., SyntheticMarket]:
    return lambda **kwargs: synthetic_market(calendar, **kwargs)


# ---------------------------------------------------------------- the sample pipeline
@dataclass
class CliRun:
    data_dir: Path
    exit_code: int
    output: str


def cli(args: list[str], data_dir: Path) -> CliRun:
    from nsefc.cli import app

    result = CliRunner().invoke(
        app, args, env={"NSEFC_DATA_DIR": str(data_dir)}, catch_exceptions=False
    )
    return CliRun(data_dir, result.exit_code, result.output)


@pytest.fixture(scope="session")
def sample_run(tmp_path_factory: pytest.TempPathFactory) -> CliRun:
    """`nsefc run --sample --no-serve` once, shared by the pipeline tests (§16.5)."""
    data_dir = tmp_path_factory.mktemp("sample-data")
    return cli(["run", "--sample", "--no-serve"], data_dir)
