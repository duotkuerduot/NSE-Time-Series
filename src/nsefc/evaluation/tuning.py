"""Hyperparameter tuning for the full profile (§11.1, §11.2): Optuna TPE on the tuning period.

Expanding-window annual folds: for each year in the tuning period, fit on every labelled row
before 1 January and score the year's out-of-sample MAE. The objective is the mean over
folds. Tuning-period results are never used for selection; the tuned values are written to
the evaluation report so a maintainer can freeze them in config/models/ (§10.2).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from nsefc.config import ModelSpec
from nsefc.evaluation.dataset import ModelData, members_at, test_rows, training_rows
from nsefc.models import Forecaster, ModelUnavailable
from nsefc.targets import winsorise


def _suggest(trial: Any, name: str, space: dict[str, Any]) -> Any:
    if "choices" in space:
        return trial.suggest_categorical(name, list(space["choices"]))
    low, high = space["low"], space["high"]
    if space.get("integer"):
        return trial.suggest_int(name, int(low), int(high), log=bool(space.get("log", False)))
    return trial.suggest_float(name, float(low), float(high), log=bool(space.get("log", False)))


def folds(
    data: ModelData, tuning: tuple[date, date], winsorise_limit: float
) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    out = []
    held = data.held
    for year in range(tuning[0].year, tuning[1].year + 1):
        start = held[int(held.searchsorted(pd.Timestamp(year=year, month=1, day=1)))]
        end = pd.Timestamp(year=year + 1, month=1, day=1)
        train = training_rows(data.table, start).sort_values(
            ["session_date", "ticker"], kind="stable"
        )
        train = train.assign(y=winsorise(train["y"].to_numpy(dtype=float), winsorise_limit))
        test = test_rows(data.table, start, end, members_at(data.table, start))
        if len(train) and len(test):
            out.append((train, test))
    return out


def tune(
    data: ModelData,
    model_id: str,
    *,
    factory_for: Callable[[dict[str, Any]], Callable[[], Forecaster]],
    spec: ModelSpec,
    tuning: tuple[date, date],
    trials: int,
    seed: int,
    winsorise_limit: float,
) -> dict[str, Any]:
    try:
        import optuna
    except ImportError as exc:
        raise ModelUnavailable(
            "the full profile needs Optuna: run `uv run --extra full nsefc run --profile full`"
        ) from exc
    optuna.logging.set_verbosity(optuna.logging.WARNING)
    splits = folds(data, tuning, winsorise_limit)
    if not splits:
        return dict(spec.frozen)

    def objective(trial: Any) -> float:
        params = dict(spec.frozen)
        for name, space in spec.search.items():
            params[name] = _suggest(trial, name, space)
        errors = []
        for train, test in splits:
            model = factory_for(params)()
            model.fit(train)
            errors.append(
                float(np.mean(np.abs(model.predict(test) - test["y"].to_numpy(dtype=float))))
            )
        return float(np.mean(errors))

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=trials)
    return {**spec.frozen, **study.best_params}
