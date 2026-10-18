"""The target: the next-session simple return.

    y(i, T) = C(i, T+1) / C(i, T) - 1,   T+1 = the next held session in which i is listed

If the security does not trade at T+1 its close is unchanged, so y = 0 and the row is kept:
an unchanged price is exactly what will be reported. A row has no label when the T+1 move is a
PRC-01 event, or when a missing session lies between T and T+1. Training labels are
winsorised; evaluation never is.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def next_session_labels(bars: pd.DataFrame) -> pd.DataFrame:
    """One label per (ticker, session_date) row of a panel sorted by (ticker, session_date).

    Needs ``ticker, session_date, close, is_event, missing_before``, as produced by
    ``features.load_panel``. Returns ``target_session``, ``y`` and ``label_ok``.
    """
    same_ticker = bars["ticker"].shift(-1) == bars["ticker"]
    next_close = bars["close"].shift(-1)
    next_session = bars["session_date"].shift(-1)
    next_event = bars["is_event"].shift(-1).fillna(False).astype(bool)
    gap = bars["missing_before"].shift(-1) - bars["missing_before"]
    label_ok = same_ticker & ~next_event & (gap == 0)
    y = (next_close / bars["close"] - 1).where(label_ok)
    return pd.DataFrame(
        {
            "ticker": bars["ticker"].to_numpy(),
            "session_date": bars["session_date"].to_numpy(),
            "target_session": next_session.where(same_ticker).to_numpy(),
            "y": y.to_numpy(),
            "label_ok": label_ok.to_numpy(),
        }
    )


def winsorise(y: np.ndarray, limit: float) -> np.ndarray:
    """Clip training labels at ±limit (±10.5% by default)."""
    return np.asarray(np.clip(y, -limit, limit), dtype=float)
