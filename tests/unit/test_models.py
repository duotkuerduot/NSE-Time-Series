"""Baselines (§10.1) and the candidate pipelines (§10.2)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nsefc.models import (
    AR1,
    CANDIDATES,
    Drift,
    HuberModel,
    MovingAverage,
    NoChange,
    RidgeModel,
    family_rank,
    lad_line,
)


def test_simple_baselines() -> None:
    test = pd.DataFrame({"b1_drift": [0.001, np.nan], "trend_5": [0.05, -0.02]})
    assert NoChange().predict(test).tolist() == [0.0, 0.0]
    assert Drift().predict(test).tolist() == [0.001, 0.0]
    assert MovingAverage().predict(test) == pytest.approx([1 / 1.05 - 1, 1 / 0.98 - 1])


def test_lad_line_resists_outliers() -> None:
    rng = np.random.default_rng(1)
    x = rng.normal(0, 0.02, 400)
    y = 0.0005 + 0.3 * x + rng.laplace(0, 0.005, 400)
    y[:20] += 0.5  # gross outliers
    a, b = lad_line(x, y)
    assert b == pytest.approx(0.3, abs=0.05) and a == pytest.approx(0.0005, abs=0.002)


def test_ar1_is_per_security_and_needs_enough_pairs() -> None:
    rng = np.random.default_rng(2)
    rows = []
    for ticker, phi in (("A", 0.4), ("B", -0.2)):
        x = rng.normal(0, 0.02, 600)
        rows.append(
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "session_date": pd.bdate_range("2020-01-01", periods=600),
                    "x_ret": x,
                    "y": phi * x + rng.normal(0, 0.005, 600),
                }
            )
        )
    rows.append(
        pd.DataFrame(
            {
                "ticker": "C",
                "session_date": pd.bdate_range("2020-01-01", periods=10),
                "x_ret": 0.01,
                "y": 0.01,
            }
        )
    )
    train = pd.concat(rows, ignore_index=True)
    model = AR1(window=500).fit(train)
    assert model.coefficients["A"][1] == pytest.approx(0.4, abs=0.05)
    assert model.coefficients["B"][1] == pytest.approx(-0.2, abs=0.05)
    assert "C" not in model.coefficients  # fewer than 50 pairs: no-change forecast
    test = pd.DataFrame({"ticker": ["A", "C", "D"], "x_ret": [0.01, 0.01, np.nan]})
    pred = model.predict(test)
    assert pred[0] == pytest.approx(0.004, abs=0.001) and pred[1] == 0.0 and pred[2] == 0.0


def table(n: int = 600, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(
        {
            "ret_1": rng.normal(0, 0.02, n),
            "vol_5": rng.uniform(0.005, 0.03, n),
            "day_of_week": rng.integers(0, 5, n).astype(float),
            "sector_code": rng.integers(0, 3, n).astype(float),
        }
    )
    frame.loc[::17, "vol_5"] = np.nan  # missing values are imputed in-fold
    frame["y"] = 0.2 * frame["ret_1"] + rng.normal(0, 0.01, n)
    return frame


@pytest.mark.parametrize("cls", [RidgeModel, HuberModel])
def test_linear_pipelines_learn_and_handle_gaps(cls: type) -> None:
    train = table()
    model = cls(
        params={"alpha": 1e-4} if cls is HuberModel else {"alpha": 1.0},
        features=["ret_1", "vol_5", "day_of_week", "sector_code"],
        categorical=["day_of_week", "sector_code"],
    )
    model.fit(train)
    test = table(seed=4)
    pred = model.predict(test)
    assert np.isfinite(pred).all()
    assert np.corrcoef(pred, test["ret_1"])[0, 1] > 0.9
    unseen = test.assign(sector_code=99.0)  # an unseen category is ignored, not an error
    assert np.isfinite(model.predict(unseen)).all()


def test_family_order_prefers_simpler_models() -> None:
    assert (
        family_rank("B3") < family_rank("ridge") <= family_rank("huber") < family_rank("lightgbm")
    )
    assert family_rank("lightgbm") < family_rank("catboost")
    assert set(CANDIDATES) == {"ridge", "huber", "lightgbm", "catboost"}
