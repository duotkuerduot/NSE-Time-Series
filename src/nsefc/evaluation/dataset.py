"""The modelling table: features, labels, point-in-time universe and baseline inputs.

One row per (ticker, session). Everything is as of the row's session: the universe flags use
trailing windows ending at the row (rule L6), and the baseline helpers (``b1_drift`` and
``x_ret``) only look backwards.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from nsefc.domain import InstrumentType
from nsefc.features import FeatureSpec, Panel, build
from nsefc.intervals import floor_sigma
from nsefc.targets import next_session_labels


@dataclass(frozen=True, slots=True)
class UniverseRule:
    window: int = 250
    min_traded_share: float = 0.80
    min_median_turnover_kes: float = 1_000_000
    min_history: int = 500


@dataclass(slots=True)
class ModelData:
    table: pd.DataFrame
    features: list[str]
    categorical: list[str]
    held: pd.DatetimeIndex

    def held_index(self, day: pd.Timestamp) -> int:
        return int(self.held.searchsorted(day))


def _per_ticker(
    values: pd.Series, tickers: pd.Series, window: int, how: str, min_periods: int
) -> pd.Series:
    rolled = values.groupby(tickers, sort=False).rolling(window, min_periods=min_periods)
    out: pd.Series = getattr(rolled, how)()
    flat: pd.Series = out.reset_index(level=0, drop=True).sort_index()
    return flat


def universe_flags(panel: Panel, rule: UniverseRule) -> pd.DataFrame:
    """Point-in-time forecast-universe membership for every row (§13.1)."""
    bars = panel.bars
    tickers = bars["ticker"]
    pos = bars["pos"].to_numpy()
    kinds = panel.securities.set_index("ticker")["instrument_type"]
    ordinary = tickers.map(kinds).eq(InstrumentType.ORDINARY.value).to_numpy()
    turnover = bars["turnover"].where(bars["turnover"].notna(), bars["volume"] * bars["close"])
    traded_share = _per_ticker(
        bars["traded"].astype(float), tickers, rule.window, "mean", rule.window
    )
    median_turnover = _per_ticker(
        turnover.astype(float), tickers, rule.window, "median", rule.window
    )
    history = pos + 1
    eligible = (
        ordinary
        & (traded_share.to_numpy() >= rule.min_traded_share)
        & (median_turnover.to_numpy() >= rule.min_median_turnover_kes)
        & (history >= rule.min_history)
    )
    return pd.DataFrame(
        {
            "in_universe": eligible,
            "is_ordinary": ordinary,
            "traded_share_250": traded_share.to_numpy(),
            "median_turnover_250": median_turnover.to_numpy(),
        }
    )


def build_model_data(
    panel: Panel,
    spec: FeatureSpec,
    rule: UniverseRule,
    *,
    sigma_floor: float,
    drift_window: int = 250,
) -> ModelData:
    features = build(panel, spec)
    labels = next_session_labels(panel.bars)
    universe = universe_flags(panel, rule)
    bars = panel.bars
    table = features.copy()
    for column in ("target_session", "y", "label_ok"):
        table[column] = labels[column].to_numpy()
    for column in universe.columns:
        table[column] = universe[column].to_numpy()
    table["close"] = bars["close"].to_numpy(dtype=float)
    table["traded"] = bars["traded"].to_numpy()
    table["is_event"] = bars["is_event"].to_numpy()
    table["held_k"] = bars["held_k"].to_numpy()

    # Today's simple return, only when it is a clean one-session move (B3 input, x_ret).
    previous_close = bars["close"].shift(1)
    same = bars["ticker"].shift(1) == bars["ticker"]
    no_gap = bars["missing_before"].diff() == 0
    clean = same & no_gap & ~bars["is_event"]
    x_ret = (bars["close"] / previous_close - 1).where(clean)
    table["x_ret"] = x_ret.to_numpy()
    table["b1_drift"] = _per_ticker(x_ret, bars["ticker"], drift_window, "mean", 60).to_numpy()
    table["sigma"] = floor_sigma(table["ewma_vol"].to_numpy(), sigma_floor)
    table["year"] = table["session_date"].dt.year
    held = panel.held
    return ModelData(table=table, features=spec.columns(), categorical=spec.categorical, held=held)


def refit_dates(
    held: pd.DatetimeIndex, start: pd.Timestamp, end: pd.Timestamp, frequency: str
) -> list[pd.Timestamp]:
    """The first held session on or after each period boundary in [start, end]."""
    months = {"monthly": 1, "quarterly": 3, "semiannual": 6, "annual": 12}[frequency]
    boundary = pd.Timestamp(year=start.year, month=1, day=1)
    while boundary + pd.DateOffset(months=months) <= start:
        boundary += pd.DateOffset(months=months)
    dates: list[pd.Timestamp] = []
    while boundary <= end:
        k = int(held.searchsorted(max(boundary, start)))
        if k < len(held) and held[k] <= end:
            day = held[k]
            if not dates or day > dates[-1]:
                dates.append(day)
        boundary += pd.DateOffset(months=months)
    return dates


def training_rows(table: pd.DataFrame, before: pd.Timestamp) -> pd.DataFrame:
    """Labelled, gap-guarded universe rows with origin strictly before ``before`` (rule L5)."""
    mask = (
        (table["session_date"] < before)
        & table["label_ok"]
        & table["window_ok"]
        & table["in_universe"]
        & table["y"].notna()
    )
    return table[mask]


def test_rows(
    table: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, members: set[str]
) -> pd.DataFrame:
    """Rows to forecast in [start, end): tickers in the universe at the refit date."""
    mask = (
        (table["session_date"] >= start)
        & (table["session_date"] < end)
        & table["label_ok"]
        & table["window_ok"]
        & table["ticker"].isin(members)
        & table["y"].notna()
    )
    return table[mask]


def members_at(table: pd.DataFrame, day: pd.Timestamp) -> set[str]:
    rows = table[(table["session_date"] == day) & table["in_universe"]]
    return set(rows["ticker"].astype(str))


def nan_safe(values: np.ndarray) -> np.ndarray:
    return np.where(np.isfinite(values), values, 0.0)
