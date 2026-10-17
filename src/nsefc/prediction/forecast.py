"""The forward forecast (§11.2 "Forecast", §12, §13.1).

The champion, refitted on all labelled data, forecasts the session after the last data date
for every security in the forecast universe at that date. Its 80% range is calibrated on the
champion's own most recent 250 sessions of out-of-sample walk-forward predictions. Every
universe security gets a forecast or a reason why not (AC-09).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from nsefc.domain import UnavailableReason
from nsefc.evaluation import ModelData, members_at
from nsefc.intervals import interval, static_quantiles
from nsefc.models import Forecaster


@dataclass(slots=True)
class Forecast:
    origin: pd.Timestamp
    target: pd.Timestamp
    target_from_calendar: bool
    rows: pd.DataFrame  # forecasts for universe members that passed the gap guard
    unavailable: pd.DataFrame  # ticker, reason


def calibration_scores(walkforward: pd.DataFrame, model_id: str, window: int) -> np.ndarray:
    """Scores (y - y_hat) / sigma from the champion's last ``window`` sessions of predictions."""
    rows = walkforward[walkforward["model_id"] == model_id]
    if rows.empty:
        return np.array([])
    last_k = rows["held_k"].max()
    recent = rows[rows["held_k"] > last_k - window]
    scores: np.ndarray = ((recent["y"] - recent["y_hat"]) / recent["sigma"]).to_numpy(dtype=float)
    return scores


def forward_forecast(
    data: ModelData,
    model: Forecaster,
    *,
    scores: np.ndarray,
    level: float,
    band: float,
    target: pd.Timestamp,
    target_from_calendar: bool,
    max_lookback: int = 60,
) -> Forecast:
    table = data.table
    origin = data.held[-1]
    members = members_at(table, origin)
    at_origin = table[table["session_date"] == origin]
    in_universe = at_origin[at_origin["ticker"].isin(members)]
    ready = in_universe[in_universe["window_ok"]]
    blocked = in_universe[~in_universe["window_ok"]]

    q_low, q_high = static_quantiles(scores, level)
    y_hat = model.predict(ready) if len(ready) else np.array([])
    sigma = ready["sigma"].to_numpy(dtype=float)
    point, lower, upper = interval(
        y_hat, sigma, np.full(len(ready), q_low), np.full(len(ready), q_high), band
    )
    close = ready["close"].to_numpy(dtype=float)
    rows = (
        pd.DataFrame(
            {
                "ticker": ready["ticker"].to_numpy(),
                "origin_session": origin,
                "target_session": target,
                "last_close": close,
                "predicted_return": point,
                "predicted_close": close * (1 + point),
                "lower": close * (1 + lower),
                "upper": close * (1 + upper),
                "return_lower": lower,
                "return_upper": upper,
                "sigma": sigma,
            }
        )
        .sort_values("ticker")
        .reset_index(drop=True)
    )

    reasons = []
    for _, row in blocked.iterrows():
        recent = table[(table["ticker"] == row["ticker"]) & (table["session_date"] <= origin)].tail(
            max_lookback
        )
        reason = (
            UnavailableReason.RECENT_PRICE_EVENT
            if recent["is_event"].any()
            else UnavailableReason.INSUFFICIENT_HISTORY
        )
        reasons.append({"ticker": row["ticker"], "reason": reason.value})
    unavailable = pd.DataFrame(reasons, columns=["ticker", "reason"])
    return Forecast(origin, target, target_from_calendar, rows, unavailable)
