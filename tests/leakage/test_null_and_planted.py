"""The harness on data with a known answer.

* Random walks: no model may show significant skill; any skill means a bug (a leak).
* Planted AR(1) returns: the harness must find roughly the skill theory predicts, and the AR(1)
  baseline must win or tie.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from nsefc.config import load_settings
from nsefc.evaluation import (
    UniverseRule,
    add_intervals,
    build_model_data,
    calibrated,
    paired_dm,
    period_metrics,
    walk_forward,
)
from nsefc.features import FeatureSpec
from nsefc.models import AR1, Drift, LightGBMModel, MovingAverage, NoChange, RidgeModel, family_rank
from nsefc.selection import Assessment, evaluate_gates, plausibility
from tests.conftest import ROOT, synthetic_market

SETTINGS = load_settings("test", project_root=ROOT, environ={})
RULE = UniverseRule(window=250, min_traded_share=0.8, min_median_turnover_kes=0, min_history=250)


def run_harness(calendar, phi: float, seed: int):  # type: ignore[no-untyped-def]
    market = synthetic_market(calendar, tickers=16, sessions=1300, phi=phi, sigma=0.015, seed=seed)
    data = build_model_data(market.panel(), FeatureSpec(), RULE, sigma_floor=0.0025)
    spec = SETTINGS.model_specs
    feats, cats = list(data.features), list(data.categorical)
    lgb_params = {**spec["lightgbm"].frozen, "n_estimators": 300, "min_data_in_leaf": 300}
    factories = {
        "B0": lambda: NoChange(),
        "B1": lambda: Drift(),
        "B2": lambda: MovingAverage(),
        "B3": lambda: AR1(window=500),
        "ridge": lambda: RidgeModel(
            params=dict(spec["ridge"].frozen), features=feats, categorical=cats
        ),
        "lightgbm": lambda: LightGBMModel(
            params=lgb_params, features=feats, categorical=cats, seed=1, threads=1
        ),
    }
    held = data.held
    result = walk_forward(
        data, factories, start=held[300], end=held[-2], frequency="annual", winsorise_limit=0.105
    )
    predictions = calibrated(add_intervals(result.predictions, window=250, level=0.8, band=0.10))
    selection = predictions[predictions["session_date"] >= held[550]]
    metrics = {m: period_metrics(g, lags=5, flat=0.001) for m, g in selection.groupby("model_id")}
    return selection, metrics


@pytest.fixture(scope="module")
def null_run(calendar):  # type: ignore[no-untyped-def]
    return run_harness(calendar, phi=0.0, seed=11)


@pytest.fixture(scope="module")
def planted_run(calendar):  # type: ignore[no-untyped-def]
    return run_harness(calendar, phi=0.25, seed=12)


def test_random_walks_show_no_significant_skill(null_run) -> None:  # type: ignore[no-untyped-def]
    selection, metrics = null_run
    for model_id, m in metrics.items():
        if model_id == "B0":
            continue
        significant = m.skill >= 0.01 and m.dm_p < 0.05
        assert not significant, f"{model_id}: skill {m.skill:.2%}, p = {m.dm_p:.3f} on pure noise"
    assessments = [Assessment(mid, mid, family_rank(mid), m, None) for mid, m in metrics.items()]
    evaluate_gates(
        assessments,
        SETTINGS.gates,
        integrity={},
        paired_p=lambda a, b: paired_dm(
            selection[selection["model_id"] == a], selection[selection["model_id"] == b], 5
        ),
    )
    assert not any(a.gates["G-SKILL"].passed for a in assessments if a.model_id != "B0")
    assert plausibility(assessments, SETTINGS.gates) == []


def test_planted_ar1_skill_is_found_and_the_baseline_wins_or_ties(planted_run) -> None:  # type: ignore[no-untyped-def]
    selection, metrics = planted_run
    theory = 1 - math.sqrt(1 - 0.25**2)  # optimal MAE skill for Gaussian AR(1): about 3.2%
    b3 = metrics["B3"]
    assert 0.5 * theory < b3.skill < 1.5 * theory, f"B3 skill {b3.skill:.2%}, theory {theory:.2%}"
    assert b3.dm_p < 0.01
    assert b3.direction.accuracy > 0.55
    for model_id in ("ridge", "lightgbm"):
        better = paired_dm(
            selection[selection["model_id"] == model_id],
            selection[selection["model_id"] == "B3"],
            5,
        )
        assert not better < 0.05, (
            f"{model_id} significantly beats the AR(1) baseline (p = {better:.3f})"
        )
    assert metrics["B2"].skill < b3.skill and metrics["B1"].skill < b3.skill


def test_intervals_are_calibrated_out_of_sample(planted_run) -> None:  # type: ignore[no-untyped-def]
    _selection, metrics = planted_run
    for model_id in ("B0", "B3", "ridge"):
        assert 0.75 <= metrics[model_id].coverage <= 0.85, (model_id, metrics[model_id].coverage)


def test_the_universe_rule_is_point_in_time(calendar) -> None:  # type: ignore[no-untyped-def]
    market = synthetic_market(calendar, tickers=3, sessions=400, seed=5)
    data = build_model_data(market.panel(), FeatureSpec(), RULE, sigma_floor=0.0025)
    table = data.table
    first_member = table[table["in_universe"]].groupby("ticker")["session_date"].min()
    held = data.held
    # min_history 250: nobody can be a member before its 250th session.
    assert (first_member >= held[249]).all()
    # Truncating the data does not change membership on earlier days (rule L6).
    cut = held[320]
    truncated = build_model_data(
        market.panel(as_of=cut), FeatureSpec(), RULE, sigma_floor=0.0025
    ).table
    merged = table[table["session_date"] <= cut].merge(
        truncated, on=["ticker", "session_date"], suffixes=("", "_t")
    )
    assert (merged["in_universe"] == merged["in_universe_t"]).all()
    assert len(merged) == len(truncated)
    assert pd.api.types.is_bool_dtype(merged["in_universe"])
    assert np.isfinite(merged["sigma"]).all()
