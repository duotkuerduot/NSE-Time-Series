"""Metrics (§11.3). Errors are in return space, so |e| is the miss as a share of last close.

* MAE skill against the no-change guess, pooled over all (security, session) rows: primary.
* Diebold-Mariano: one-sided, on the daily cross-sectional mean loss differential, with a
  Newey-West variance (5 lags).
* Directional accuracy on non-flat rows, against always-up, always-down and last-sign.
* 80% interval coverage and mean width; skill by year, by security and by regime.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


def mae(errors: np.ndarray) -> float:
    return float(np.mean(np.abs(errors))) if len(errors) else float("nan")


def skill(mae_model: float, mae_base: float) -> float:
    return 1.0 - mae_model / mae_base if mae_base > 0 else float("nan")


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def newey_west_variance(d: np.ndarray, lags: int) -> float:
    d = d - d.mean()
    n = len(d)
    variance = float(np.dot(d, d) / n)
    for lag in range(1, min(lags, n - 1) + 1):
        weight = 1.0 - lag / (lags + 1.0)
        variance += 2.0 * weight * float(np.dot(d[lag:], d[:-lag]) / n)
    return max(variance, 0.0)


def diebold_mariano(
    sessions: np.ndarray, loss_model: np.ndarray, loss_base: np.ndarray, lags: int
) -> tuple[float, float]:
    """One-sided DM test that the model's loss is lower. Returns (statistic, p-value).

    The loss differential is averaged across securities within each session first, so the
    test respects the cross-sectional dependence of same-day forecasts.
    """
    frame = pd.DataFrame({"s": sessions, "d": loss_model - loss_base})
    daily = frame.groupby("s", sort=True)["d"].mean().to_numpy()
    n = len(daily)
    if n < 10:
        return float("nan"), float("nan")
    variance = newey_west_variance(daily, lags)
    if variance <= 0:
        mean = float(daily.mean())
        return (float("-inf"), 0.0) if mean < 0 else (float("inf"), 1.0)
    stat = float(daily.mean() / math.sqrt(variance / n))
    return stat, _normal_cdf(stat)


@dataclass(slots=True)
class Direction:
    accuracy: float
    coverage: float
    n: int
    always_up: float
    always_down: float
    last_sign: float

    @property
    def best_trivial(self) -> float:
        rates = [r for r in (self.always_up, self.always_down, self.last_sign) if math.isfinite(r)]
        return max(rates) if rates else float("nan")

    def worse_than_trivial(self, alpha: float) -> bool:
        """One-sided z-test: is the model's hit rate significantly below the best trivial one?"""
        if self.n == 0 or not np.isfinite(self.accuracy):
            return False
        p = self.best_trivial
        if p <= 0 or p >= 1:
            return False
        z = (self.accuracy - p) / math.sqrt(p * (1 - p) / self.n)
        return _normal_cdf(z) < alpha


def direction(y: np.ndarray, y_hat: np.ndarray, x_ret: np.ndarray, flat: float) -> Direction:
    """Accuracy on rows where the actual changed and the forecast is outside ±flat."""
    moved = y != 0
    called = np.abs(y_hat) > flat
    rows = moved & called
    n = int(rows.sum())
    total = int(moved.sum())
    if n == 0:
        return Direction(float("nan"), 0.0, 0, float("nan"), float("nan"), float("nan"))
    actual = np.sign(y[rows])
    last = np.sign(x_ret[rows])
    # "Sign of the last return" makes no call after an unchanged or unknown day: score it only
    # where it calls, as the model is scored only where it calls.
    calls_last = np.isfinite(last) & (last != 0)
    return Direction(
        accuracy=float(np.mean(np.sign(y_hat[rows]) == actual)),
        coverage=n / total if total else 0.0,
        n=n,
        always_up=float(np.mean(actual > 0)),
        always_down=float(np.mean(actual < 0)),
        last_sign=float(np.mean(last[calls_last] == actual[calls_last]))
        if calls_last.any()
        else float("nan"),
    )


@dataclass(slots=True)
class PeriodMetrics:
    rows: int
    sessions: int
    securities: int
    mae: float
    mae_b0: float
    skill: float
    dm_stat: float
    dm_p: float
    coverage: float
    width: float
    direction: Direction
    skill_by_year: dict[int, float] = field(default_factory=dict)
    security_skill: dict[str, float] = field(default_factory=dict)

    @property
    def share_securities_non_negative(self) -> float:
        values = [v for v in self.security_skill.values() if np.isfinite(v)]
        return float(np.mean([v >= 0 for v in values])) if values else float("nan")

    def as_dict(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "sessions": self.sessions,
            "securities": self.securities,
            "mae": self.mae,
            "mae_b0": self.mae_b0,
            "skill": self.skill,
            "dm_stat": self.dm_stat,
            "dm_p": self.dm_p,
            "coverage": self.coverage,
            "width": self.width,
            "direction": {
                "accuracy": self.direction.accuracy,
                "coverage": self.direction.coverage,
                "n": self.direction.n,
                "always_up": self.direction.always_up,
                "always_down": self.direction.always_down,
                "last_sign": self.direction.last_sign,
            },
            "skill_by_year": {str(k): v for k, v in self.skill_by_year.items()},
            "share_securities_non_negative": self.share_securities_non_negative,
        }


def period_metrics(rows: pd.DataFrame, *, lags: int, flat: float) -> PeriodMetrics:
    """Metrics for one model over one period. ``rows`` has y, y_hat, lower, upper, x_ret,
    ticker, session_date and year (the no-change error is |y|)."""
    y = rows["y"].to_numpy(dtype=float)
    y_hat = rows["y_hat"].to_numpy(dtype=float)
    e_model = np.abs(y_hat - y)
    e_base = np.abs(y)
    model_mae, base_mae = float(e_model.mean()), float(e_base.mean())
    stat, p = diebold_mariano(rows["session_date"].to_numpy(), e_model, e_base, lags)
    inside = (rows["lower"] <= rows["y"]) & (rows["y"] <= rows["upper"])
    by_year = {}
    for year, group in rows.assign(em=e_model, eb=e_base).groupby("year"):
        by_year[int(str(year))] = skill(float(group["em"].mean()), float(group["eb"].mean()))
    by_security = {}
    for ticker, group in rows.assign(em=e_model, eb=e_base).groupby("ticker"):
        by_security[str(ticker)] = skill(float(group["em"].mean()), float(group["eb"].mean()))
    return PeriodMetrics(
        rows=len(rows),
        sessions=int(rows["session_date"].nunique()),
        securities=int(rows["ticker"].nunique()),
        mae=model_mae,
        mae_b0=base_mae,
        skill=skill(model_mae, base_mae),
        dm_stat=stat,
        dm_p=p,
        coverage=float(inside.mean()) if len(rows) else float("nan"),
        width=float((rows["upper"] - rows["lower"]).mean()) if len(rows) else float("nan"),
        direction=direction(y, y_hat, rows["x_ret"].to_numpy(dtype=float), flat),
        skill_by_year=by_year,
        security_skill=by_security,
    )


def paired_dm(rows_a: pd.DataFrame, rows_b: pd.DataFrame, lags: int) -> float:
    """p-value that model a beats model b on the same rows (one-sided DM)."""
    keys = ["ticker", "session_date"]
    merged = rows_a[[*keys, "y", "y_hat"]].merge(
        rows_b[[*keys, "y_hat"]], on=keys, suffixes=("_a", "_b")
    )
    if merged.empty:
        return float("nan")
    loss_a = (merged["y_hat_a"] - merged["y"]).abs().to_numpy(dtype=float)
    loss_b = (merged["y_hat_b"] - merged["y"]).abs().to_numpy(dtype=float)
    return diebold_mariano(merged["session_date"].to_numpy(), loss_a, loss_b, lags)[1]


def breakdown(rows: pd.DataFrame, column: str, labels: list[str]) -> dict[str, float]:
    """Skill vs no-change by tercile of ``column`` (report only)."""
    if rows.empty or rows[column].nunique() < 3:
        return {}
    bins = pd.qcut(rows[column].rank(method="first"), 3, labels=labels)
    out = {}
    for label, group in rows.groupby(bins, observed=True):
        out[str(label)] = skill(
            float(np.abs(group["y_hat"] - group["y"]).mean()), float(np.abs(group["y"]).mean())
        )
    return out
