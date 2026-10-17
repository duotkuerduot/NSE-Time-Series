"""Synthetic sample dataset in the Mendeley file format (ENGINEERING.md §16.3).

About 30 fictional tickers (SMPL01 to SMPL30, clearly not real companies) trading over the
NSE calendar from 2015 to 2024. The prices behave like NSE closes: each is a session VWAP,
so returns carry mild positive autocorrelation, and many stocks trade thinly. The data also
contains the defects the real dataset has, so every correction and check is exercised:

* a missing-session gap (no rows for any security for several weeks);
* band-breaching events (a 2-for-1 split and a one-day data spike);
* identical duplicate rows;
* one session's block of rows dated a Saturday, fixed by a ``redate`` correction;
* a rights line (``SMPL05-R``) that must stay out of the forecast universe;
* index rows (``^NASI``) for the market features.

Generation is deterministic (fixed seed, two-decimal formatting, ``\\n`` line endings), so the
files and their SHA-256 hashes are identical on Windows, macOS and Linux. The generator runs
at acquisition time; nothing it produces is committed.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np

from nsefc.calendar import TradingCalendar

GENERATOR_VERSION = 1
SEED = 20261016
FIRST_DAY = date(2015, 1, 1)
LAST_DAY = date(2024, 12, 31)
N_TICKERS = 30
HEADER = [
    "Date",
    "Code",
    "Name",
    "12m Low",
    "12m High",
    "Day Low",
    "Day High",
    "Day Price",
    "Previous",
    "Change",
    "Change%",
    "Volume",
    "Adjusted Price",
]
SECTORS = [
    "Banking",
    "Manufacturing",
    "Agricultural",
    "Energy",
    "Telecommunication",
    "Insurance",
    "Commercial and Services",
    "Construction",
]

# Planted defects (their effects are asserted in tests/unit/test_sample.py).
GAP = (date(2019, 7, 1), date(2019, 7, 26))  # missing sessions: no rows at all
SPLIT = ("SMPL07", date(2020, 3, 2))  # 2-for-1 split: the price halves
SPIKE = ("SMPL12", date(2016, 9, 6))  # a one-day +40% data error
DUPLICATED_SESSION = date(2016, 3, 15)  # three rows repeated verbatim
MISDATED = (date(2017, 6, 13), date(2017, 6, 10))  # the 13 June block is dated Saturday 10 June
RIGHTS = ("SMPL05-R", date(2018, 5, 2), 8)  # rights line: first session, sessions


@dataclass(frozen=True, slots=True)
class SampleTicker:
    code: str
    name: str
    sector: str
    start_price: float
    sigma: float  # daily volatility of the latent price
    beta: float  # loading on the market factor
    lag: float  # VWAP lag: share of today's move that shows up tomorrow
    trade_prob: float  # chance of trading on a session
    volume_scale: float  # median shares traded when it trades


def _tickers(rng: np.random.Generator) -> list[SampleTicker]:
    out = []
    for i in range(1, N_TICKERS + 1):
        liquid = i <= 22
        out.append(
            SampleTicker(
                code=f"SMPL{i:02d}",
                name=f"Sample Company {i:02d} Ltd",
                sector=SECTORS[(i - 1) % len(SECTORS)],
                start_price=float(np.round(rng.uniform(5, 250), 2)),
                sigma=float(rng.uniform(0.008, 0.022)),
                beta=float(rng.uniform(0.3, 1.1)),
                lag=float(rng.uniform(0.12, 0.24)),
                trade_prob=float(rng.uniform(0.92, 1.0) if liquid else rng.uniform(0.25, 0.7)),
                volume_scale=float(
                    rng.uniform(40_000, 900_000) if liquid else rng.uniform(500, 8_000)
                ),
            )
        )
    return out


def _fmt_price(value: float) -> str:
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _fmt_int(value: int) -> str:
    return f"{value:,}"


def _fmt_date(day: date) -> str:
    return day.strftime("%d-%b-%y")


@dataclass(slots=True)
class _Row:
    day: date
    code: str
    name: str
    low12: float
    high12: float
    low: float
    high: float
    price: float
    previous: float
    volume: int

    def cells(self, written_date: date | None = None) -> list[str]:
        change = self.price - self.previous
        unchanged = abs(change) < 0.005
        return [
            _fmt_date(written_date or self.day),
            self.code,
            self.name,
            _fmt_price(self.low12),
            _fmt_price(self.high12),
            _fmt_price(self.low),
            _fmt_price(self.high),
            _fmt_price(self.price),
            _fmt_price(self.previous),
            "-" if unchanged else _fmt_price(change),
            "-" if unchanged else f"{abs(change) / self.previous:.2%}",
            "-" if self.volume == 0 else _fmt_int(self.volume),
            "-",
        ]


def _simulate(calendar: TradingCalendar) -> tuple[list[_Row], list[SampleTicker]]:
    rng = np.random.default_rng(SEED)
    tickers = _tickers(rng)
    sessions = calendar.sessions_in(FIRST_DAY, LAST_DAY)
    n = len(sessions)
    market = rng.standard_t(5, size=n) * 0.006
    rows: list[_Row] = []
    index_level = 100.0
    index_rows: list[_Row] = []
    closes_by_session: dict[date, list[float]] = {}
    for ticker in tickers:
        idio = rng.standard_t(4, size=n) * ticker.sigma / np.sqrt(2.0)
        latent = np.log(ticker.start_price) + np.cumsum(ticker.beta * market + idio)
        trades = rng.random(n) < ticker.trade_prob
        volumes = np.maximum(1, rng.lognormal(np.log(ticker.volume_scale), 0.8, size=n)).astype(int)
        spreads = rng.uniform(0.002, 0.02, size=(n, 2))
        price = ticker.start_price
        scale = 1.0  # becomes 0.5 from the split session on
        history: list[float] = []
        for t, day in enumerate(sessions):
            previous = price
            if (ticker.code, day) == SPLIT:
                scale = 0.5
                price = round(previous * scale, 2)
                volume, low, high = int(volumes[t]), price, price
            elif trades[t] or t == 0:
                # A VWAP sits between yesterday's and today's latent price.
                lagged = ticker.lag * (latent[t] - latent[t - 1]) if t else 0.0
                vwap = scale * float(np.exp(latent[t] - lagged))
                move = float(np.clip(vwap / previous - 1, -0.095, 0.095))
                price = max(round(previous * (1 + move), 2), 0.5)
                volume = int(volumes[t])
                low = round(price * (1 - spreads[t, 0]), 2)
                high = round(price * (1 + spreads[t, 1]), 2)
            else:
                volume, low, high = 0, price, price
            history.append(price)
            window = history[-250:]
            rows.append(
                _Row(
                    day,
                    ticker.code,
                    ticker.name,
                    min(window),
                    max(window),
                    low,
                    high,
                    price,
                    previous,
                    volume,
                )
            )
            closes_by_session.setdefault(day, []).append(price / previous - 1)
    # Spike: one session's close is wrong by +40%, and the next session reverts.
    for k, row in enumerate(rows):
        if (row.code, row.day) == SPIKE:
            rows[k] = _Row(
                row.day,
                row.code,
                row.name,
                row.low12,
                row.high12 * 1.4,
                row.low,
                round(row.price * 1.4, 2),
                round(row.price * 1.4, 2),
                row.previous,
                row.volume or 100,
            )
            nxt = rows[k + 1]
            rows[k + 1] = _Row(
                nxt.day,
                nxt.code,
                nxt.name,
                nxt.low12,
                nxt.high12,
                nxt.low,
                nxt.high,
                nxt.price,
                round(row.price * 1.4, 2),
                nxt.volume,
            )
    for day in sessions:
        index_level *= 1 + float(np.mean(closes_by_session[day]))
        level = round(index_level, 2)
        index_rows.append(
            _Row(
                day, "^NASI", "Sample All-Share Index", level, level, level, level, level, level, 0
            )
        )
    # Index "Previous" values chain from the prior level.
    for k in range(1, len(index_rows)):
        index_rows[k].previous = index_rows[k - 1].price
    rows.extend(index_rows)
    # Rights line: a few sessions of a separately quoted SMPL05 rights entitlement.
    code, first, count = RIGHTS
    start = sessions.index(first)
    for day in sessions[start : start + count]:
        rows.append(
            _Row(day, code, "Sample Company 05 Ltd (Rights)", 1.0, 3.0, 1.5, 2.5, 2.0, 2.0, 5_000)
        )
    return rows, tickers


def generate(target: Path, calendar: TradingCalendar) -> list[Path]:
    """Write the sample files into ``target``; returns their paths, sorted."""
    rows, tickers = _simulate(calendar)
    rows = [r for r in rows if not (GAP[0] <= r.day <= GAP[1])]
    rows.sort(key=lambda r: (r.day, r.code))
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for year in range(FIRST_DAY.year, LAST_DAY.year + 1):
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(HEADER)
        for row in (r for r in rows if r.day.year == year):
            written_date = MISDATED[1] if row.day == MISDATED[0] else None
            writer.writerow(row.cells(written_date))
            if row.day == DUPLICATED_SESSION and row.code in {"SMPL03", "SMPL04", "SMPL09"}:
                writer.writerow(row.cells())
        path = target / f"NSE_data_all_stocks_{year}.csv"
        path.write_bytes(buffer.getvalue().encode("utf-8"))
        written.append(path)
    sectors = io.StringIO(newline="")
    writer = csv.writer(sectors, lineterminator="\n")
    writer.writerow(["SECTOR", "CODE", "NAME"])
    for ticker in tickers:
        writer.writerow([ticker.sector, ticker.code, ticker.name])
    sector_path = target / f"NSE_data_stock_market_sectors_{LAST_DAY.year}.csv"
    sector_path.write_bytes(sectors.getvalue().encode("utf-8"))
    written.append(sector_path)
    return sorted(written)


def misdated_session_offset() -> timedelta:
    return MISDATED[0] - MISDATED[1]
