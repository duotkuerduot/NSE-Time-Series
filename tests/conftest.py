from __future__ import annotations

from pathlib import Path

import pytest

from nsefc.calendar import TradingCalendar, load_calendar

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def calendar() -> TradingCalendar:
    return load_calendar(ROOT / "config" / "calendar" / "nse_holidays.yaml")
