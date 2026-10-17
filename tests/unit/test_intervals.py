"""Volatility-scaled split conformal intervals (§12)."""

from __future__ import annotations

import numpy as np
import pytest

from nsefc.intervals import (
    floor_sigma,
    interval,
    quantile_levels,
    rolling_quantiles,
    static_quantiles,
)


def test_floor_and_levels() -> None:
    assert floor_sigma(np.array([0.001, 0.02, np.nan]), 0.0025).tolist() == [0.0025, 0.02, 0.0025]
    assert quantile_levels(0.8) == pytest.approx((0.1, 0.9))


def test_rolling_quantiles_use_only_earlier_origins() -> None:
    k = np.repeat(np.arange(400), 3).astype(float)
    scores = np.random.default_rng(0).normal(size=len(k))
    low, high = rolling_quantiles(k, scores, window=250, level=0.8, min_scores=100)
    assert np.isnan(low[:3]).all()  # nothing earlier yet
    row = 3 * 300
    past = scores[(k >= 300 - 250) & (k < 300)]
    assert low[row] == pytest.approx(np.quantile(past, 0.1))
    assert high[row] == pytest.approx(np.quantile(past, 0.9))
    # Changing today's and later scores never changes today's quantiles.
    changed = scores.copy()
    changed[k >= 300] = 50.0
    low2, high2 = rolling_quantiles(k, changed, window=250, level=0.8, min_scores=100)
    assert low2[row] == low[row] and high2[row] == high[row]


def test_interval_is_ordered_and_clipped_to_the_band() -> None:
    point, lower, upper = interval(
        np.array([0.0, 0.2, -0.05]),
        np.array([0.02, 0.02, 0.5]),
        np.array([-1.3, -1.3, -1.3]),
        np.array([1.3, 1.3, 1.3]),
        band=0.10,
    )
    assert point.tolist() == pytest.approx([0.0, 0.10, -0.05])
    assert (lower <= point).all() and (point <= upper).all()
    assert lower.min() >= -0.10 and upper.max() <= 0.10
    # Quantiles of the wrong sign never put the point outside its own range.
    p, lo, hi = interval(
        np.array([0.0]), np.array([0.01]), np.array([0.5]), np.array([-0.5]), band=0.1
    )
    assert lo[0] == p[0] == hi[0] == 0.0


def test_conformal_coverage_on_matching_data() -> None:
    rng = np.random.default_rng(4)
    sigma = rng.uniform(0.005, 0.03, 20000)
    y = rng.standard_t(4, 20000) * sigma
    q_low, q_high = static_quantiles(y[:10000] / sigma[:10000], 0.8)
    _p, lower, upper = interval(
        np.zeros(10000), sigma[10000:], np.full(10000, q_low), np.full(10000, q_high), 1.0
    )
    covered = ((y[10000:] >= lower) & (y[10000:] <= upper)).mean()
    assert 0.78 < covered < 0.82
    with pytest.raises(ValueError, match="no calibration"):
        static_quantiles(np.array([np.nan]), 0.8)
