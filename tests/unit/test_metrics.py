"""Metrics: MAE skill, the Diebold-Mariano test and directional calls."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from nsefc.evaluation import (
    diebold_mariano,
    direction,
    mae,
    newey_west_variance,
    paired_dm,
    period_metrics,
    skill,
)


def test_mae_and_skill() -> None:
    assert mae(np.array([0.01, -0.03])) == pytest.approx(0.02)
    assert skill(0.0099, 0.01) == pytest.approx(0.01)
    assert skill(0.011, 0.01) == pytest.approx(-0.1)
    assert math.isnan(skill(0.01, 0.0))


def test_newey_west_with_no_lags_is_the_variance() -> None:
    d = np.random.default_rng(1).normal(size=500)
    assert newey_west_variance(d, 0) == pytest.approx(np.var(d))
    # Positive autocorrelation raises the long-run variance.
    smooth = np.convolve(d, np.ones(5) / 5, mode="valid")
    assert newey_west_variance(smooth, 5) > newey_west_variance(smooth, 0)


def test_dm_detects_a_consistently_better_model() -> None:
    rng = np.random.default_rng(2)
    sessions = np.repeat(np.arange(300), 10)
    base = np.abs(rng.normal(0, 0.02, len(sessions)))
    better = base * 0.9
    stat, p = diebold_mariano(sessions, better, base, 5)
    assert stat < 0 and p < 0.001
    other = base + rng.normal(0, 1e-3, len(base))
    _s1, p_ab = diebold_mariano(sessions, other, base, 5)
    _s2, p_ba = diebold_mariano(sessions, base, other, 5)
    assert p_ab + p_ba == pytest.approx(1.0)  # one-sided in each direction
    assert math.isnan(diebold_mariano(np.arange(5), base[:5], base[:5], 5)[1])  # too few sessions


def test_direction_counts_only_non_flat_calls() -> None:
    y = np.array([0.01, -0.02, 0.0, 0.03, -0.01])
    y_hat = np.array([0.005, 0.004, 0.01, 0.0005, -0.002])  # 4th is inside ±0.1%: no call
    x_ret = np.array([0.01, 0.01, -0.01, 0.02, -0.03])
    d = direction(y, y_hat, x_ret, 0.001)
    assert d.n == 3 and d.accuracy == pytest.approx(2 / 3)
    assert d.coverage == pytest.approx(3 / 4)  # 4 rows moved, 3 called
    assert d.always_up == pytest.approx(1 / 3) and d.last_sign == pytest.approx(2 / 3)
    assert not d.worse_than_trivial(0.05)


def test_direction_worse_than_trivial() -> None:
    n = 2000
    y = np.where(np.arange(n) % 10 < 7, 0.01, -0.01)  # 70% up: always-up scores 0.7
    y_hat = np.where(np.arange(n) % 2 == 0, 0.01, -0.01)  # a coin flip
    d = direction(y, y_hat, np.zeros(n), 0.001)
    assert d.best_trivial == pytest.approx(0.7)
    assert d.worse_than_trivial(0.05)


def frame(n_sessions: int = 120, tickers: int = 5, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2020-01-01", periods=n_sessions)
    rows = pd.DataFrame(
        {
            "session_date": np.repeat(days, tickers),
            "ticker": np.tile([f"T{i}" for i in range(tickers)], n_sessions),
            "y": rng.normal(0, 0.015, n_sessions * tickers),
            "x_ret": rng.normal(0, 0.015, n_sessions * tickers),
        }
    )
    rows["y_hat"] = 0.3 * rows["y"]  # a model that knows a little
    rows["lower"], rows["upper"] = rows["y_hat"] - 0.02, rows["y_hat"] + 0.02
    rows["year"] = rows["session_date"].dt.year
    return rows


def test_period_metrics() -> None:
    rows = frame()
    m = period_metrics(rows, lags=5, flat=0.001)
    assert m.rows == len(rows) and m.securities == 5 and m.sessions == 120
    assert m.mae_b0 == pytest.approx(np.abs(rows["y"]).mean())
    assert m.skill == pytest.approx(1 - np.abs(rows["y_hat"] - rows["y"]).mean() / m.mae_b0)
    assert m.skill > 0 and m.dm_p < 0.001
    assert set(m.skill_by_year) == {2020}
    assert 0 <= m.coverage <= 1 and m.width == pytest.approx(0.04)
    as_dict = m.as_dict()
    assert as_dict["direction"]["n"] == m.direction.n and "skill_by_year" in as_dict


def test_paired_dm_compares_on_the_same_rows() -> None:
    rows = frame()
    worse = rows.assign(y_hat=0.0)
    assert paired_dm(rows, worse, 5) < 0.01
    assert paired_dm(worse, rows, 5) > 0.99


def test_the_last_sign_rule_is_scored_only_where_it_calls() -> None:
    y = np.array([0.01, -0.01, 0.02, -0.02])
    y_hat = np.array([0.01, -0.01, 0.01, 0.01])
    x_ret = np.array([0.01, 0.0, np.nan, -0.01])  # no call after an unchanged or unknown day
    d = direction(y, y_hat, x_ret, 0.001)
    assert d.last_sign == pytest.approx(1.0)  # right on both rows where it calls
    assert d.best_trivial == pytest.approx(1.0)
    none = direction(y, y_hat, np.zeros(4), 0.001)
    assert math.isnan(none.last_sign) and none.best_trivial == pytest.approx(0.5)
