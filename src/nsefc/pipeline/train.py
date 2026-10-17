"""Stage 3, train and evaluate (§10-§12): walk-forward for every model, gates, champion."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nsefc.config import Settings
from nsefc.evaluation import (
    ModelData,
    PeriodMetrics,
    UniverseRule,
    add_intervals,
    breakdown,
    build_model_data,
    calibrated,
    members_at,
    paired_dm,
    period_metrics,
    refit_dates,
    training_rows,
    walk_forward,
)
from nsefc.evaluation.tuning import tune
from nsefc.features import FeatureSpec, load_panel
from nsefc.models import (
    AR1,
    BASELINES,
    CANDIDATES,
    ArtifactError,
    Drift,
    Forecaster,
    MovingAverage,
    NoChange,
    family_rank,
    load_artifact,
    save_artifact,
)
from nsefc.pipeline.context import RunContext, StageError
from nsefc.selection import (
    Assessment,
    choose_champion,
    evaluate_gates,
    plausibility,
)
from nsefc.storage import atomic_write_json, read_table, write_table
from nsefc.targets import winsorise

BASELINE_LABELS = {
    "B0": "No-change guess",
    "B1": "Drift baseline",
    "B2": "5-session average baseline",
    "B3": "AR(1) baseline",
}


def feature_spec(settings: Settings) -> FeatureSpec:
    f = settings.features
    return FeatureSpec(
        returns=tuple(f.returns),
        sma=tuple(f.sma),
        high_low_window=f.high_low_window,
        volatility_windows=tuple(f.volatility_windows),
        ewma_lambda=f.ewma_lambda,
        liquidity_window=f.liquidity_window,
        market_returns=tuple(f.market_returns),
        max_lookback=f.max_lookback,
    )


def universe_rule(settings: Settings) -> UniverseRule:
    u = settings.universe
    return UniverseRule(u.window, u.min_traded_share, u.min_median_turnover_kes, u.min_history)


def load_canonical(ctx: RunContext) -> dict[str, pd.DataFrame]:
    layout = ctx.layout
    paths = {
        "bars": layout.bars,
        "sessions": layout.sessions,
        "indices": layout.indices,
        "securities": layout.securities,
    }
    missing = [str(p) for p in paths.values() if not p.is_file()]
    if missing:
        raise StageError("no canonical data yet: run `nsefc ingest` (or `nsefc run`) first", 2)
    return {name: read_table(path) for name, path in paths.items()}


def model_data(ctx: RunContext, features_fp: str) -> ModelData:
    """Build the modelling table, or reuse the cached copy for this feature fingerprint."""
    spec = feature_spec(ctx.settings)
    canonical = load_canonical(ctx)
    sessions = canonical["sessions"]
    held = pd.DatetimeIndex(sessions.loc[sessions["status"] == "held", "session_date"])
    cache = ctx.layout.features / features_fp[:16] / "table.parquet"
    if cache.is_file() and not ctx.force:
        return ModelData(read_table(cache), spec.columns(), spec.categorical, held)
    panel = load_panel(
        bars=canonical["bars"],
        sessions=canonical["sessions"],
        indices=canonical["indices"],
        securities=canonical["securities"],
        calendar=ctx.calendar,
    )
    data = build_model_data(
        panel,
        spec,
        universe_rule(ctx.settings),
        sigma_floor=ctx.settings.intervals.sigma_floor,
        drift_window=ctx.settings.models.b1_window,
    )
    write_table(data.table, cache)
    return data


def hyperparameters(settings: Settings, model_id: str) -> dict[str, Any]:
    return dict(settings.model_specs[model_id].frozen)


def _factory_with(
    settings: Settings, model_id: str, data: ModelData, params: dict[str, Any]
) -> Callable[[], Forecaster]:
    """``factory`` with the hyperparameters last, for tuning trials."""
    return factory(settings, model_id, data, params)


def factory(
    settings: Settings, model_id: str, data: ModelData, params: dict[str, Any] | None = None
) -> Callable[[], Forecaster]:
    runtime = settings.runtime
    if model_id == "B0":
        return lambda: NoChange(label=BASELINE_LABELS["B0"])
    if model_id == "B1":
        return lambda: Drift(label=BASELINE_LABELS["B1"])
    if model_id == "B2":
        return lambda: MovingAverage(label=BASELINE_LABELS["B2"])
    if model_id == "B3":
        return lambda: AR1(label=BASELINE_LABELS["B3"], window=settings.models.b3_window)
    cls = CANDIDATES[model_id]
    spec = settings.model_specs[model_id]
    chosen = dict(params if params is not None else spec.frozen)

    def make() -> Forecaster:
        model = cls(
            label=spec.label,
            params=dict(chosen),
            features=list(data.features),
            categorical=list(data.categorical),
            seed=runtime.seed,
            threads=runtime.threads,
        )
        if hasattr(model, "early_stopping_share"):
            model.early_stopping_share = settings.models.early_stopping_share
        return model

    return make


def tune_candidates(
    ctx: RunContext, data: ModelData, candidates: list[str], trials: int
) -> dict[str, dict[str, Any]]:
    """Tune on the tuning period only (§11.2) and save the values at once, so a later stop
    (G-PLAUS, say) never loses them: ``data/models/<run_id>/tuned.json``."""
    s = ctx.settings
    tuned: dict[str, dict[str, Any]] = {}
    for model_id in candidates:
        if not s.model_specs[model_id].search:
            continue
        ctx.echo(
            f"tuning {model_id} on {s.periods.tuning[0]} to {s.periods.tuning[1]} ({trials} trials)"
        )
        tuned[model_id] = tune(
            data,
            model_id,
            factory_for=partial(_factory_with, s, model_id, data),
            spec=s.model_specs[model_id],
            tuning=s.periods.tuning,
            trials=trials,
            seed=s.runtime.seed,
            winsorise_limit=s.targets.winsorise,
        )
        atomic_write_json(
            ctx.layout.models / ctx.run_id / "tuned.json",
            {
                "tuning_period": [str(d) for d in s.periods.tuning],
                "trials": trials,
                "models": tuned,
            },
        )
    return tuned


@dataclass(slots=True)
class TrainOutputs:
    run_id: str
    evaluation: dict[str, Any]
    champion_path: Path
    walkforward_path: Path


def _metrics_dict(metrics: PeriodMetrics | None) -> dict[str, Any] | None:
    return None if metrics is None else metrics.as_dict()


def _integrity(
    model: Forecaster,
    path: Path,
    sample: pd.DataFrame,
    metadata: dict[str, Any],
    rows: pd.DataFrame,
) -> tuple[bool, str]:
    """G-INT: hash round trip, finite predictions, ordered bounds."""
    save_artifact(model, path, metadata)
    try:
        reloaded = load_artifact(path)
    except ArtifactError as exc:
        return False, str(exc)
    if len(sample):
        before, after = model.predict(sample), reloaded.predict(sample)
        if not np.allclose(before, after, rtol=0, atol=1e-9):
            return False, "reloaded artifact does not reproduce its predictions"
    if not np.isfinite(rows["y_hat"]).all():
        return False, "predictions contain NaN or infinity"
    rows = rows[np.isfinite(rows["lower"]) & np.isfinite(rows["upper"])]
    if ((rows["lower"] > rows["y_hat"] + 1e-12) | (rows["y_hat"] > rows["upper"] + 1e-12)).any():
        return False, "a range does not contain its own forecast"
    return True, "artifact hash verified; reload reproduces predictions within 1e-9"


def run_training(ctx: RunContext, data: ModelData, *, dataset_info: dict[str, Any]) -> TrainOutputs:
    s = ctx.settings
    layout = ctx.layout
    profile = s.profiles["full" if ctx.profile == "full" else "default"]
    held = data.held
    selection_start, selection_end = (pd.Timestamp(d) for d in s.periods.selection)
    holdout_start = pd.Timestamp(s.periods.holdout_start)
    last_origin = held[-2] if len(held) > 1 else held[-1]
    if held[0] > selection_start or last_origin < holdout_start:
        raise StageError(
            f"the data ({held[0].date()} to {held[-1].date()}) does not cover the evaluation "
            f"periods in the configuration (selection from {selection_start.date()}, holdout from "
            f"{holdout_start.date()})",
            30,
        )
    k0 = max(int(held.searchsorted(selection_start)) - s.periods.calibration_warmup_sessions, 1)
    start = held[k0]
    started = time.monotonic()

    tuned: dict[str, dict[str, Any]] = {}
    if profile.tune:
        tuned = tune_candidates(ctx, data, list(profile.candidates), profile.trials)
    factories = {m: factory(s, m, data) for m in BASELINES}
    for model_id in profile.candidates:
        factories[model_id] = factory(s, model_id, data, tuned.get(model_id))

    result = walk_forward(
        data,
        factories,
        start=start,
        end=last_origin,
        frequency=profile.refit,
        winsorise_limit=s.targets.winsorise,
        progress=ctx.echo if ctx.verbose else None,
    )
    for skipped, reason in result.unavailable.items():
        ctx.echo(f"warning: {skipped} skipped: {reason}")
    predictions = add_intervals(
        result.predictions,
        window=s.intervals.calibration_window,
        level=s.intervals.level,
        band=s.quality.band,
    )
    run_models = layout.models / ctx.run_id
    run_predictions = layout.predictions / ctx.run_id
    walkforward_path = run_predictions / "walkforward.parquet"
    write_table(predictions, walkforward_path)

    usable = calibrated(predictions)
    sel = usable[
        (usable["session_date"] >= selection_start) & (usable["session_date"] <= selection_end)
    ]
    hold = usable[usable["session_date"] >= holdout_start]
    by_model = {
        str(m): (g_sel, hold[hold["model_id"] == m]) for m, g_sel in sel.groupby("model_id")
    }
    lags, flat = s.evaluation.dm_lags, s.evaluation.flat_threshold
    metrics: dict[str, tuple[PeriodMetrics, PeriodMetrics | None]] = {}
    for mid, (rows_sel, rows_hold) in by_model.items():
        metrics[mid] = (
            period_metrics(rows_sel, lags=lags, flat=flat),
            period_metrics(rows_hold, lags=lags, flat=flat) if len(rows_hold) else None,
        )

    integrity: dict[str, tuple[bool, str]] = {}
    last_window = predictions[predictions["refit_date"] == result.refits[-1]]
    sample_rows = data.table.merge(
        last_window[["ticker", "session_date"]].drop_duplicates(), on=["ticker", "session_date"]
    )
    for mid, model in result.last_fits.items():
        if mid in ("B0", "B1", "B2") or mid not in metrics:
            continue
        rows = predictions[predictions["model_id"] == mid]  # before calibrated() drops rows
        integrity[mid] = _integrity(
            model,
            run_models / f"{mid}.joblib",
            sample_rows,
            {
                "role": "last walk-forward fit",
                "refit_date": str(result.refits[-1].date()),
                "dataset": dataset_info,
            },
            rows,
        )

    cache: dict[tuple[str, str], float] = {}

    def paired_p(a: str, b: str) -> float:
        if (a, b) not in cache:
            cache[(a, b)] = paired_dm(sel[sel["model_id"] == a], sel[sel["model_id"] == b], lags)
        return cache[(a, b)]

    labels = {
        **BASELINE_LABELS,
        **{m: s.model_specs[m].label for m in CANDIDATES if m in s.model_specs},
    }
    assessments = [
        Assessment(m, labels[m], family_rank(m), metrics[m][0], metrics[m][1])
        for m in [*BASELINES, *CANDIDATES]
        if m in metrics
    ]
    evaluate_gates(assessments, s.gates, integrity=integrity, paired_p=paired_p)
    suspicious = plausibility(assessments, s.gates)
    if suspicious:
        raise StageError(
            "G-PLAUS: suspected leakage; results are better than plausible: "
            + "; ".join(suspicious),
            30,
        )
    choice = choose_champion(assessments, s.gates, paired_p=paired_p)

    # Refit the champion on every labelled row and save it for the forecast (§11.2).
    champion_id = choice.champion
    everything = training_rows(data.table, held[-1] + pd.Timedelta(days=1)).sort_values(
        ["session_date", "ticker"], kind="stable"
    )
    everything = everything.assign(
        y=winsorise(everything["y"].to_numpy(dtype=float), s.targets.winsorise)
    )
    champion = factories[champion_id]()
    champion.fit(everything)
    champion_path = run_models / "champion.joblib"
    save_artifact(
        champion,
        champion_path,
        {
            "role": "champion",
            "champion": champion_id,
            "training_window": [
                str(everything["session_date"].min().date()),
                str(everything["session_date"].max().date()),
            ],
            "dataset": dataset_info,
        },
    )

    refit_sizes = [
        len(members_at(data.table, d)) for d in refit_dates(held, start, last_origin, profile.refit)
    ]
    span = data.table[
        data.table["in_universe"]
        & (data.table["session_date"] >= start)
        & (data.table["session_date"] <= last_origin)
    ]
    finite = [
        v
        for a in assessments
        for period in (a.selection, a.holdout)
        if period is not None
        for v in (period.skill,)
        if math.isfinite(v)
    ]
    accuracies = [
        v
        for a in assessments
        for period in (a.selection, a.holdout)
        if period is not None
        for v in (period.direction.accuracy,)
        if math.isfinite(v)
    ]
    champion_hold = hold[hold["model_id"] == champion_id]
    evaluation = {
        "profile": ctx.profile,
        "refit": profile.refit,
        "periods": {
            "selection": [str(selection_start.date()), str(selection_end.date())],
            "holdout": [str(holdout_start.date()), str(last_origin.date())],
            "calibration_warmup_start": str(start.date()),
        },
        "dataset": dataset_info,
        "universe": {
            "min": min(refit_sizes),
            "max": max(refit_sizes),
            "median": int(np.median(refit_sizes)),
            "at_last_session": len(members_at(data.table, held[-1])),
        },
        "refits": len(result.refits),
        "champion": {
            "model_id": champion_id,
            "label": labels[champion_id],
            "reason": choice.reason,
        },
        "models": [
            {
                "model_id": a.model_id,
                "label": a.label,
                "family_rank": a.family_rank,
                "selection": _metrics_dict(a.selection),
                "holdout": _metrics_dict(a.holdout),
                "gates": [g.as_dict() for g in a.gates.values()],
                "notes": a.notes,
            }
            for a in assessments
        ],
        "plausibility": {
            "triggered": False,
            "skill_max": s.gates.plaus_skill_max,
            "direction_max": s.gates.plaus_direction_max,
            "highest_skill": max(finite, default=float("nan")),
            "highest_direction": max(accuracies, default=float("nan")),
        },
        "rows": {
            "universe_rows": len(span),
            "gap_guard_excluded": int((~span["window_ok"]).sum()),
            "unlabelled": int((span["window_ok"] & ~span["label_ok"]).sum()),
        },
        "tuned": tuned,
        "unavailable": result.unavailable,
        "breakdowns": {
            "liquidity (traded share)": breakdown(
                champion_hold, "traded_share_250", ["low", "mid", "high"]
            ),
            "volatility": breakdown(champion_hold, "sigma", ["calm", "normal", "volatile"]),
        },
        "seconds": round(time.monotonic() - started, 1),
    }
    return TrainOutputs(ctx.run_id, evaluation, champion_path, walkforward_path)


def finite(value: float) -> float | None:
    return value if isinstance(value, float) and math.isfinite(value) else None
