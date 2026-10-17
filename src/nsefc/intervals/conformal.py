"""Volatility-scaled split conformal intervals (§12).

1. sigma = EWMA volatility of the security's returns up to T, floored at 0.25%.
2. Scores s = (y - y_hat) / sigma from the most recent 250 sessions of out-of-sample
   walk-forward predictions, pooled across the universe. Never in-sample residuals.
3. Interval [y_hat + q_lo(s) sigma, y_hat + q_hi(s) sigma] in return space, clipped to the
   price band, then mapped to price with C_T x (1 + bound).
4. In walk-forward evaluation the calibration window rolls forward, so a session's interval
   only uses scores whose actuals were known by that session.
"""

from __future__ import annotations

import numpy as np


def floor_sigma(ewma_vol: np.ndarray, floor: float) -> np.ndarray:
    sigma = np.asarray(ewma_vol, dtype=float)
    return np.where(np.isfinite(sigma), np.maximum(sigma, floor), floor)


def quantile_levels(level: float) -> tuple[float, float]:
    tail = (1.0 - level) / 2.0
    return tail, 1.0 - tail


def rolling_quantiles(
    origin_k: np.ndarray,
    scores: np.ndarray,
    window: int,
    level: float,
    *,
    min_scores: int = 100,
) -> tuple[np.ndarray, np.ndarray]:
    """Per row: score quantiles over origins in [k - window, k - 1] (actuals known at k).

    ``origin_k`` is each row's origin session as an index into the held sessions. Rows with
    fewer than ``min_scores`` usable scores get NaN.
    """
    lo_q, hi_q = quantile_levels(level)
    order = np.argsort(origin_k, kind="stable")
    sorted_k = origin_k[order]
    sorted_s = scores[order]
    finite = np.isfinite(sorted_s)
    sorted_k_f = sorted_k[finite]
    sorted_s_f = sorted_s[finite]
    low = np.full(len(origin_k), np.nan)
    high = np.full(len(origin_k), np.nan)
    unique_k, first_row = np.unique(sorted_k, return_index=True)
    bounds = [*first_row.tolist(), len(sorted_k)]
    for i, k in enumerate(unique_k):
        start = np.searchsorted(sorted_k_f, k - window, side="left")
        end = np.searchsorted(sorted_k_f, k, side="left")  # origins < k: actuals known at k
        if end - start >= min_scores:
            ql, qh = np.quantile(sorted_s_f[start:end], [lo_q, hi_q])
            rows = order[bounds[i] : bounds[i + 1]]
            low[rows], high[rows] = ql, qh
    return low, high


def interval(
    y_hat: np.ndarray,
    sigma: np.ndarray,
    q_low: np.ndarray,
    q_high: np.ndarray,
    band: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Clip the point and bounds to the band; keep lower <= point <= upper."""
    point = np.clip(y_hat, -band, band)
    lower = np.clip(point + np.minimum(q_low, 0.0) * sigma, -band, band)
    upper = np.clip(point + np.maximum(q_high, 0.0) * sigma, -band, band)
    return point, np.minimum(lower, point), np.maximum(upper, point)


def static_quantiles(scores: np.ndarray, level: float) -> tuple[float, float]:
    """Quantiles over one fixed calibration set (the forward forecast's last 250 sessions)."""
    finite = scores[np.isfinite(scores)]
    lo_q, hi_q = quantile_levels(level)
    if len(finite) == 0:
        raise ValueError("no calibration scores")
    ql, qh = np.quantile(finite, [lo_q, hi_q])
    return float(ql), float(qh)
