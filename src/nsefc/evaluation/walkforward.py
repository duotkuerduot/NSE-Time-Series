"""Walk-forward evaluation (§11.2): expanding training windows, periodic refits.

At each refit date R every model is fitted on labelled rows with origin before R (so the
training window ends at least one session before the test window, rule L5) and then
forecasts every origin in [R, next refit) for the securities in the universe at R. The
procedure is the same in the selection period and the holdout; the calibration warm-up before
the selection period only feeds the conformal intervals.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from nsefc.evaluation.dataset import ModelData, members_at, refit_dates, test_rows, training_rows
from nsefc.intervals import interval, rolling_quantiles
from nsefc.models import Forecaster, ModelUnavailable
from nsefc.targets import winsorise

Factory = Callable[[], Forecaster]
Progress = Callable[[str], None]


@dataclass(slots=True)
class WalkForwardResult:
    predictions: pd.DataFrame
    last_fits: dict[str, Forecaster]
    refits: list[pd.Timestamp]
    unavailable: dict[str, str] = field(default_factory=dict)


def walk_forward(
    data: ModelData,
    factories: dict[str, Factory],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    frequency: str,
    winsorise_limit: float,
    progress: Progress | None = None,
) -> WalkForwardResult:
    table = data.table
    refits = refit_dates(data.held, start, end, frequency)
    if not refits:
        raise ValueError(f"no refit dates between {start.date()} and {end.date()}")
    pieces: list[pd.DataFrame] = []
    last_fits: dict[str, Forecaster] = {}
    unavailable: dict[str, str] = {}
    for i, refit in enumerate(refits):
        window_end = refits[i + 1] if i + 1 < len(refits) else end + pd.Timedelta(days=1)
        train = training_rows(table, refit).sort_values(["session_date", "ticker"], kind="stable")
        train = train.assign(y=winsorise(train["y"].to_numpy(dtype=float), winsorise_limit))
        members = members_at(table, refit)
        test = test_rows(table, refit, window_end, members).sort_values(
            ["session_date", "ticker"], kind="stable"
        )
        if progress:
            progress(
                f"refit {i + 1}/{len(refits)} at {refit.date()}: {len(train):,} training rows, "
                f"{len(test):,} forecasts for {len(members)} securities"
            )
        if test.empty:
            continue
        for model_id, factory in factories.items():
            if model_id in unavailable:
                continue
            model = factory()
            try:
                model.fit(train)
            except ModelUnavailable as exc:
                unavailable[model_id] = str(exc)
                continue
            y_hat = model.predict(test)
            last_fits[model_id] = model
            pieces.append(
                pd.DataFrame(
                    {
                        "model_id": model_id,
                        "ticker": test["ticker"].to_numpy(),
                        "session_date": test["session_date"].to_numpy(),
                        "target_session": test["target_session"].to_numpy(),
                        "held_k": test["held_k"].to_numpy(),
                        "refit_date": refit,
                        "y_hat": y_hat,
                        "y": test["y"].to_numpy(dtype=float),
                        "sigma": test["sigma"].to_numpy(dtype=float),
                        "x_ret": test["x_ret"].to_numpy(dtype=float),
                        "close": test["close"].to_numpy(dtype=float),
                        "traded_share_250": test["traded_share_250"].to_numpy(dtype=float),
                        "year": test["year"].to_numpy(),
                    }
                )
            )
    predictions = pd.concat(pieces, ignore_index=True) if pieces else pd.DataFrame()
    return WalkForwardResult(predictions, last_fits, refits, unavailable)


def add_intervals(
    predictions: pd.DataFrame, *, window: int, level: float, band: float
) -> pd.DataFrame:
    """Rolling conformal intervals per model (§12 step 4): only past scores calibrate."""
    out = []
    for _model_id, group in predictions.groupby("model_id", sort=True):
        group = group.copy()
        scores = ((group["y"] - group["y_hat"]) / group["sigma"]).to_numpy(dtype=float)
        q_low, q_high = rolling_quantiles(
            group["held_k"].to_numpy(dtype=float), scores, window, level
        )
        point, lower, upper = interval(
            group["y_hat"].to_numpy(dtype=float),
            group["sigma"].to_numpy(dtype=float),
            q_low,
            q_high,
            band,
        )
        group["y_hat"] = point
        group["q_low"], group["q_high"] = q_low, q_high
        group["lower"], group["upper"] = lower, upper
        out.append(group)
    return pd.concat(out, ignore_index=True)


def calibrated(predictions: pd.DataFrame) -> pd.DataFrame:
    """Rows whose interval could be calibrated (warm-up rows without enough history drop out)."""
    usable: pd.DataFrame = predictions[
        np.isfinite(predictions["lower"]) & np.isfinite(predictions["upper"])
    ]
    return usable
