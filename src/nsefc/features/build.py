"""Feature set v1 (§8.2) and the gap guard (§8.4).

One code path for training and prediction: ``build(panel)`` returns one row per (ticker,
session) with every feature as of that session. Every input is scale-free (returns, ratios,
normalised quantities) and every window counts trading sessions, never calendar days.

Rows are sorted by (ticker, session_date) and contiguous per ticker, so a rolling window over
the whole column is correct wherever the row's position within its ticker (``pos``) is at
least the window length minus one; earlier positions are set to null (rule L3: nothing
crosses from one security into the next).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from nsefc.domain import InstrumentType
from nsefc.features.panel import Panel


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    returns: tuple[int, ...] = (1, 2, 3, 5, 10, 20)
    sma: tuple[int, ...] = (5, 20, 50)
    high_low_window: int = 250
    volatility_windows: tuple[int, ...] = (5, 20)
    ewma_lambda: float = 0.94
    liquidity_window: int = 20
    market_returns: tuple[int, ...] = (1, 5)
    max_lookback: int = 60

    def columns(self) -> list[str]:
        cols = [f"ret_{k}" for k in self.returns]
        cols += [f"trend_{n}" for n in self.sma]
        cols += [f"dist_high_{self.high_low_window}", f"dist_low_{self.high_low_window}"]
        cols += [f"vol_{w}" for w in self.volatility_windows]
        cols += ["ewma_vol", "hl_range"]
        cols += ["log_volume", "volume_vs_median", "traded_share", "sessions_since_trade"]
        cols += [f"mkt_ret_{k}" for k in self.market_returns] + ["breadth"]
        cols += [f"nasi_ret_{k}" for k in self.market_returns]
        cols += ["day_of_week", "days_to_next_session", "sector_code"]
        return cols

    @property
    def categorical(self) -> list[str]:
        return ["day_of_week", "sector_code"]


def _valid(pos: np.ndarray, window: int) -> np.ndarray:
    """Rows whose last ``window`` rows all belong to the same ticker."""
    return pos >= window - 1


def _grouped_shift(values: pd.Series, pos: np.ndarray, k: int) -> pd.Series:
    shifted = values.shift(k)
    shifted[pos < k] = np.nan
    return shifted


_REDUCERS: dict[str, Callable[[np.ndarray], np.ndarray]] = {
    "mean": lambda w: np.mean(w, axis=1),
    "std": lambda w: np.std(w, axis=1, ddof=1),
    "max": lambda w: np.max(w, axis=1),
    "min": lambda w: np.min(w, axis=1),
    "median": lambda w: np.median(w, axis=1),
}


def _rolling(values: pd.Series, pos: np.ndarray, window: int, how: str) -> pd.Series:
    """A trailing statistic over exactly ``window`` rows, computed window by window.

    Each value depends only on the rows in its own window, so it cannot change when other
    securities' rows or later rows change (pandas' running sums would carry rounding from the
    rows before, about 1e-8 for a standard deviation that should be 0). A window holding a
    null gives null.
    """
    data = values.to_numpy(dtype=float)
    out = np.full(len(data), np.nan)
    if len(data) >= window:
        windows = np.lib.stride_tricks.sliding_window_view(data, window)
        out[window - 1 :] = _REDUCERS[how](windows)
    out[~_valid(pos, window)] = np.nan
    return pd.Series(out, index=values.index)


def _weighted_window_mean(values: np.ndarray, pos: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """sum_j w_j x_{t-j} / sum_j w_j over the last len(weights) rows (finite-window EWMA).

    ``values`` are one-session returns, which need the row before, so a row is valid only when
    all len(weights) returns exist: ``pos >= len(weights)``.
    """
    filled = np.where(np.isnan(values), 0.0, values)
    total = np.convolve(filled, weights)[: len(values)]
    out = total / weights.sum()
    out[pos < len(weights)] = np.nan
    return np.asarray(out, dtype=float)


def _sessions_since_trade(traded: np.ndarray, pos: np.ndarray, cap: int) -> np.ndarray:
    out = np.empty(len(traded))
    count = 0.0
    for i in range(len(traded)):
        # A new security starts counting afresh at its first row.
        count = 0.0 if traded[i] else (1.0 if pos[i] == 0 else count + 1.0)
        out[i] = min(count, cap)
    return out


def window_flags(panel: Panel, window: int) -> np.ndarray:
    """True where the last ``window`` rows of the ticker hold no missing session and no event.

    This is the gap guard (§8.4): a missing session between the first and last row of the
    window, or a PRC-01 event anywhere in it, invalidates the row.
    """
    bars = panel.bars
    pos = bars["pos"].to_numpy()
    full = _valid(pos, window)
    missing = bars["missing_before"].to_numpy(dtype=float)
    first_missing = pd.Series(missing).shift(window - 1).to_numpy()
    no_gap = (missing - first_missing) == 0
    events = (
        pd.Series(bars["is_event"].to_numpy(dtype=float)).rolling(window, min_periods=window).sum()
    )
    no_event = events.to_numpy() == 0
    return np.asarray(full & no_gap & no_event, dtype=bool)


def _market_features(panel: Panel, spec: FeatureSpec, ret: dict[int, pd.Series]) -> pd.DataFrame:
    bars = panel.bars
    ordinary = set(
        panel.securities.loc[
            panel.securities["instrument_type"] == InstrumentType.ORDINARY.value, "ticker"
        ]
    )
    frame = pd.DataFrame({"session_date": bars["session_date"], "ticker": bars["ticker"]})
    for k in spec.market_returns:
        frame[f"r{k}"] = ret[k]
    usable = bars["ticker"].isin(ordinary).to_numpy() & ~bars["is_event"].to_numpy()
    sub = frame[usable]
    grouped = sub.groupby("session_date")
    market = pd.DataFrame(index=pd.DatetimeIndex(sorted(frame["session_date"].unique())))
    for k in spec.market_returns:
        market[f"mkt_ret_{k}"] = grouped[f"r{k}"].mean()
    r1 = sub["r1"] if 1 in spec.market_returns else sub[f"r{spec.market_returns[0]}"]
    adv = (r1 > 0).groupby(sub["session_date"]).sum()
    dec = (r1 < 0).groupby(sub["session_date"]).sum()
    n = r1.notna().groupby(sub["session_date"]).sum()
    market["breadth"] = (adv - dec) / n.where(n > 0)
    # NASI log returns over held sessions; null where the index is not quoted at either end.
    held = panel.held
    nasi = panel.indices[panel.indices["index"] == "^NASI"].set_index("session_date")["level"]
    nasi = nasi.reindex(held)
    log_nasi = np.log(nasi)
    for k in spec.market_returns:
        market[f"nasi_ret_{k}"] = (log_nasi - log_nasi.shift(k)).reindex(market.index)
    # MKT-01: thin sessions get no market context.
    status = panel.sessions.set_index("session_date")
    if "market_ok" in status.columns:
        thin = ~status["market_ok"].reindex(market.index).fillna(True).astype(bool)
        market.loc[thin.to_numpy(), :] = np.nan
    return market


def build(panel: Panel, spec: FeatureSpec) -> pd.DataFrame:
    """Features for every row of the panel, plus the gap-guard flag ``window_ok``."""
    panel.assert_as_of()
    bars = panel.bars
    pos = bars["pos"].to_numpy()
    close = bars["close"].astype(float)
    log_close = pd.Series(np.log(close.to_numpy()), index=close.index)
    out = pd.DataFrame({"ticker": bars["ticker"], "session_date": bars["session_date"]})

    ret: dict[int, pd.Series] = {}
    for k in sorted(set(spec.returns) | set(spec.market_returns)):
        ret[k] = log_close - _grouped_shift(log_close, pos, k)
    for k in spec.returns:
        out[f"ret_{k}"] = ret[k]
    for n in spec.sma:
        out[f"trend_{n}"] = close / _rolling(close, pos, n, "mean") - 1
    w = spec.high_low_window
    high = _rolling(close, pos, w, "max")
    low = _rolling(close, pos, w, "min")
    long_ok = window_flags(panel, w)
    out[f"dist_high_{w}"] = np.where(long_ok, close / high - 1, np.nan)
    out[f"dist_low_{w}"] = np.where(long_ok, close / low - 1, np.nan)
    r1 = ret[1]
    for window in spec.volatility_windows:
        out[f"vol_{window}"] = _rolling(r1, pos, window, "std")
    # max_lookback closes hold max_lookback - 1 returns: the EWMA stays inside the gap guard.
    weights = spec.ewma_lambda ** np.arange(spec.max_lookback - 1)
    variance = _weighted_window_mean((r1**2).to_numpy(), pos, weights)
    out["ewma_vol"] = np.sqrt(variance)
    out["hl_range"] = (bars["high"] - bars["low"]) / close

    volume = bars["volume"].astype(float)
    lw = spec.liquidity_window
    out["log_volume"] = np.log1p(volume)
    out["volume_vs_median"] = np.log1p(volume) - np.log1p(_rolling(volume, pos, lw, "median"))
    out["traded_share"] = _rolling(bars["traded"].astype(float), pos, lw, "mean")
    out["sessions_since_trade"] = _sessions_since_trade(
        bars["traded"].to_numpy(), pos, spec.max_lookback
    )

    market = _market_features(panel, spec, ret)
    joined = market.reindex(bars["session_date"].to_numpy())
    for column in market.columns:
        out[column] = joined[column].to_numpy()

    dates = bars["session_date"]
    out["day_of_week"] = dates.dt.dayofweek.astype(float)
    unique_dates = pd.DatetimeIndex(sorted(dates.unique()))
    gaps = {}
    for day in unique_dates:
        nxt, _known = panel.calendar.next_session_or_weekday(day.date())
        gaps[day] = float((pd.Timestamp(nxt) - day).days)
    out["days_to_next_session"] = dates.map(gaps).astype(float)
    sectors = sorted(s for s in panel.securities["sector"].dropna().unique() if s)
    sector_codes = {s: float(i) for i, s in enumerate(sectors)}
    sector_of = panel.securities.set_index("ticker")["sector"].map(sector_codes)
    out["sector_code"] = bars["ticker"].map(sector_of).astype(float)

    out["window_ok"] = window_flags(panel, spec.max_lookback)
    return out[["ticker", "session_date", *spec.columns(), "window_ok"]]
