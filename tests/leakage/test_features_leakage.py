"""Leakage rules L1-L3 and the gap guard (§8.3, §8.4, §16.2).

Features at session T may use only data up to T: truncating the data at T, or changing every
row after T, must leave them exactly unchanged, and nothing may cross from one security to the
next. Comparisons are exact (NaN equals NaN): every rolling value is computed from its own
window only, so there is no rounding carried in from other rows either.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from nsefc.features import FeatureSpec, LeakageError, Panel, build
from nsefc.targets import next_session_labels
from tests.conftest import SyntheticMarket

SPEC = FeatureSpec()
COLUMNS = [*SPEC.columns(), "window_ok"]
MARKET_COLUMNS = [c for c in COLUMNS if c.startswith(("mkt_", "breadth", "nasi_"))]


def features_at(market: SyntheticMarket, day: pd.Timestamp, *, truncate: bool) -> pd.DataFrame:
    panel = market.panel(as_of=day if truncate else None)
    table = build(panel, SPEC)
    return table[table["session_date"] == day].set_index("ticker")[COLUMNS].astype(float)


def assert_same(a: pd.DataFrame, b: pd.DataFrame) -> None:
    assert a.index.equals(b.index)
    left, right = a.to_numpy(dtype=float), b.to_numpy(dtype=float)
    same = (left == right) | (np.isnan(left) & np.isnan(right))
    assert same.all(), [a.columns[j] for j in sorted(set(np.argwhere(~same)[:, 1]))]


@pytest.fixture(scope="module")
def market(calendar) -> SyntheticMarket:  # type: ignore[no-untyped-def]
    from tests.conftest import synthetic_market

    return synthetic_market(
        calendar,
        tickers=5,
        sessions=420,
        phi=0.1,
        trade_probability=0.85,
        missing=(150,),
        events=((2, 260),),
    )


@pytest.fixture(scope="module")
def full_features(market: SyntheticMarket) -> pd.DataFrame:
    return build(market.panel(), SPEC).set_index(["ticker", "session_date"])


@settings(max_examples=25, deadline=None)
@given(k=st.integers(min_value=1, max_value=418))
def test_truncation_invariance(
    market: SyntheticMarket, full_features: pd.DataFrame, k: int
) -> None:
    held = market.panel().held
    day = held[min(k, len(held) - 1)]
    truncated = features_at(market, day, truncate=True)
    reference = (
        full_features.xs(day, level="session_date")[COLUMNS].astype(float).loc[truncated.index]
    )
    assert_same(truncated, reference)


@pytest.mark.parametrize("k", [60, 200, 300, 400])
def test_changing_the_future_changes_nothing_before(market: SyntheticMarket, k: int) -> None:
    held = market.panel().held
    day = held[k]
    before = build(market.panel(), SPEC)
    rng = np.random.default_rng(k)
    bars = market.bars.copy()
    future = bars["session_date"] > day
    bars.loc[future, "close"] *= rng.uniform(0.5, 1.5, future.sum())
    bars.loc[future, "volume"] = rng.integers(0, 10, future.sum())
    bars.loc[future, "is_event"] = True
    changed = SyntheticMarket(
        bars, market.sessions, market.indices, market.securities, market.calendar
    )
    after = build(changed.panel(), SPEC)
    past = before["session_date"] <= day
    assert_same(
        before[past].set_index(["ticker", "session_date"])[COLUMNS],
        after[after["session_date"] <= day].set_index(["ticker", "session_date"])[COLUMNS],
    )


def test_nothing_crosses_between_securities(market: SyntheticMarket) -> None:
    base = build(market.panel(), SPEC).set_index(["ticker", "session_date"])
    bars = market.bars.copy()
    first = bars["ticker"] == "T00"
    bars.loc[first, "close"] *= np.linspace(0.5, 2.0, first.sum())  # T00 sorts just before T01
    bars.loc[first, "volume"] = 0
    other = build(
        SyntheticMarket(
            bars, market.sessions, market.indices, market.securities, market.calendar
        ).panel(),
        SPEC,
    ).set_index(["ticker", "session_date"])
    own = [c for c in COLUMNS if c not in MARKET_COLUMNS]
    for ticker in ("T01", "T02", "T03", "T04"):
        assert_same(base.loc[ticker, own], other.loc[ticker, own])
    # A security's first rows have no lagged values at all.
    t01 = base.loc["T01"]
    assert np.isnan(t01["ret_1"].iloc[0]) and np.isnan(t01["ret_20"].iloc[19])
    assert not np.isnan(t01["ret_20"].iloc[20])


def test_load_panel_refuses_rows_after_as_of(market: SyntheticMarket) -> None:
    panel = market.panel(as_of=market.panel().held[100])
    assert panel.bars["session_date"].max() <= panel.as_of
    leaky = Panel(
        panel.as_of,
        market.panel().bars,
        panel.sessions,
        panel.indices,
        panel.securities,
        panel.calendar,
    )
    with pytest.raises(LeakageError):
        leaky.assert_as_of()
    with pytest.raises(LeakageError):
        build(leaky, SPEC)


def test_gap_guard(market: SyntheticMarket) -> None:
    """Rows whose 60-session window holds a missing session or an event are excluded."""
    table = build(market.panel(), SPEC)
    sessions = market.sessions
    missing_day = sessions.loc[sessions["status"] == "missing", "session_date"].iloc[0]
    held = market.panel().held
    k_after = int(held.searchsorted(missing_day))  # first held session after the gap
    for ticker, rows in table.groupby("ticker"):
        ok = rows.set_index("session_date")["window_ok"]
        # Just after the missing session every window spans it; 60 rows later none does.
        assert not ok.loc[held[k_after]] and not ok.loc[held[k_after + 58]]
        assert ok.loc[held[k_after + 59]] or ticker == "T02"
    t02 = table[table["ticker"] == "T02"].set_index("session_date")["window_ok"]
    event_day = market.bars[market.bars["is_event"]]["session_date"].iloc[0]
    k_event = int(held.searchsorted(event_day))
    assert not t02.loc[held[k_event]] and not t02.loc[held[k_event + 59]]
    assert t02.loc[held[k_event + 60]]
    t03 = table[table["ticker"] == "T03"].set_index("session_date")["window_ok"]
    assert t03.loc[held[k_event]]  # another security's event does not block T03


def test_long_window_features_become_null_instead_of_blocking(market: SyntheticMarket) -> None:
    table = build(market.panel(), SPEC)
    row = table[(table["ticker"] == "T01") & table["window_ok"]].iloc[0]
    assert np.isnan(row["dist_high_250"]) and not np.isnan(row["ret_20"])


def test_labels_align_with_the_next_session(make_market: Callable[..., SyntheticMarket]) -> None:
    market = make_market(tickers=2, sessions=40, missing=(20,), events=((0, 30),))
    bars = market.panel().bars
    labels = next_session_labels(bars)
    for i in range(len(bars) - 1):
        same = bars["ticker"].iloc[i] == bars["ticker"].iloc[i + 1]
        if not same:
            assert not labels["label_ok"].iloc[i] and np.isnan(labels["y"].iloc[i])
            continue
        crosses_gap = bars["missing_before"].iloc[i + 1] != bars["missing_before"].iloc[i]
        next_event = bool(bars["is_event"].iloc[i + 1])
        assert labels["label_ok"].iloc[i] == (not crosses_gap and not next_event)
        assert labels["target_session"].iloc[i] == bars["session_date"].iloc[i + 1]
        if labels["label_ok"].iloc[i]:
            expected = bars["close"].iloc[i + 1] / bars["close"].iloc[i] - 1
            assert labels["y"].iloc[i] == pytest.approx(expected, rel=1e-12)
    assert not labels["label_ok"].iloc[-1]


def test_features_match_hand_computed_values(make_market: Callable[..., SyntheticMarket]) -> None:
    market = make_market(tickers=1, sessions=80, trade_probability=0.7, seed=3)
    panel = market.panel()
    table = build(panel, SPEC)
    bars = panel.bars
    close, volume, traded = (
        bars["close"].to_numpy(),
        bars["volume"].to_numpy(float),
        bars["traded"].to_numpy(),
    )
    i = 70
    log_c = np.log(close)
    assert table["ret_1"].iloc[i] == pytest.approx(log_c[i] - log_c[i - 1])
    assert table["ret_20"].iloc[i] == pytest.approx(log_c[i] - log_c[i - 20])
    assert table["trend_5"].iloc[i] == pytest.approx(close[i] / close[i - 4 : i + 1].mean() - 1)
    r1 = np.diff(log_c)
    assert table["vol_5"].iloc[i] == pytest.approx(np.std(r1[i - 5 : i], ddof=1))
    weights = 0.94 ** np.arange(59)
    expected_ewma = np.sqrt(np.sum(weights * r1[i - 1 - np.arange(59)] ** 2) / weights.sum())
    assert table["ewma_vol"].iloc[i] == pytest.approx(expected_ewma)
    assert table["log_volume"].iloc[i] == pytest.approx(np.log1p(volume[i]))
    assert table["volume_vs_median"].iloc[i] == pytest.approx(
        np.log1p(volume[i]) - np.log1p(np.median(volume[i - 19 : i + 1]))
    )
    assert table["traded_share"].iloc[i] == pytest.approx(traded[i - 19 : i + 1].mean())
    since = 0
    for t in traded[: i + 1]:
        since = 0 if t else since + 1
    assert table["sessions_since_trade"].iloc[i] == since
    day = bars["session_date"].iloc[i]
    assert table["day_of_week"].iloc[i] == day.dayofweek
    nxt = market.calendar.next_session(day.date())
    assert table["days_to_next_session"].iloc[i] == (pd.Timestamp(nxt) - day).days
    if traded[i]:
        assert table["hl_range"].iloc[i] == pytest.approx(
            (bars["high"].iloc[i] - bars["low"].iloc[i]) / close[i]
        )
    # With only one security, the market return is that security's return.
    assert table["mkt_ret_1"].iloc[i] == pytest.approx(table["ret_1"].iloc[i])
