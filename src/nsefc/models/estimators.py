"""Baselines and candidate models behind one small interface (§10).

Every model is a *global* forecaster of next-session simple returns, fitted on a training
frame and asked for predictions on a test frame. The frames carry the feature columns plus a
few helper columns computed as of each row (``b1_drift``, ``x_ret``), so baselines and ML
models run in exactly the same harness and can all become champion.

Determinism: fixed seeds, fixed thread counts, rows sorted before fitting, CPU only (§10.2).
"""

from __future__ import annotations

import inspect
import warnings
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import HuberRegressor, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

FAMILY_ORDER = {"baseline": 0, "linear": 1, "lightgbm": 2, "catboost": 3}


class ModelUnavailable(RuntimeError):  # noqa: N818 - names the state the CLI reports
    """An optional dependency (LightGBM, CatBoost) cannot be imported on this machine."""


@dataclass
class Forecaster:
    """Base class: ``fit(train)`` then ``predict(test)``; both frames are sorted by date."""

    name: ClassVar[str] = "base"
    family: ClassVar[str] = "baseline"
    label: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    features: list[str] = field(default_factory=list)
    categorical: list[str] = field(default_factory=list)
    seed: int = 0
    threads: int = 1
    fit_info: dict[str, Any] = field(default_factory=dict)

    def fit(self, train: pd.DataFrame) -> Forecaster:
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        raise NotImplementedError


# ---------------------------------------------------------------- baselines (§10.1)
@dataclass
class NoChange(Forecaster):
    name: ClassVar[str] = "B0"

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        return np.zeros(len(test))


@dataclass
class Drift(Forecaster):
    """Trailing 250-session mean simple return of the security (``b1_drift``)."""

    name: ClassVar[str] = "B1"

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        return test["b1_drift"].fillna(0.0).to_numpy(dtype=float)


@dataclass
class MovingAverage(Forecaster):
    """SMA_5(T) / C_T - 1: a pull back towards the recent average."""

    name: ClassVar[str] = "B2"

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        trend = test["trend_5"].to_numpy(dtype=float)
        out = 1.0 / (1.0 + trend) - 1.0
        return np.where(np.isfinite(out), out, 0.0)


def lad_line(x: np.ndarray, y: np.ndarray, iterations: int = 50) -> tuple[float, float]:
    """Least-absolute-deviations fit of y = a + b x by iteratively reweighted least squares."""
    design = np.column_stack([np.ones_like(x), x])
    weights = np.ones_like(x)
    coef = np.zeros(2)
    for _ in range(iterations):
        w = np.sqrt(weights)
        coef, *_ = np.linalg.lstsq(design * w[:, None], y * w, rcond=None)
        residual = np.abs(y - design @ coef)
        weights = 1.0 / np.maximum(residual, 1e-6)
    return float(coef[0]), float(coef[1])


@dataclass
class AR1(Forecaster):
    """Per-security AR(1) on returns, LAD fit on the trailing ``window`` sessions (B3).

    Needs ``x_ret`` (today's simple return, null when it crosses an event or a gap) and the
    label ``y``. Securities with fewer than 50 usable pairs forecast no change.
    """

    name: ClassVar[str] = "B3"
    window: int = 500
    min_pairs: int = 50
    coefficients: dict[str, tuple[float, float]] = field(default_factory=dict)

    def fit(self, train: pd.DataFrame) -> AR1:
        self.coefficients = {}
        usable = train[train["x_ret"].notna() & train["y"].notna()]
        for ticker, group in usable.groupby("ticker", sort=True):
            recent = group.sort_values("session_date").tail(self.window)
            if len(recent) < self.min_pairs:
                continue
            self.coefficients[str(ticker)] = lad_line(
                recent["x_ret"].to_numpy(dtype=float), recent["y"].to_numpy(dtype=float)
            )
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        a = test["ticker"].map(lambda t: self.coefficients.get(str(t), (0.0, 0.0))[0])
        b = test["ticker"].map(lambda t: self.coefficients.get(str(t), (0.0, 0.0))[1])
        x = test["x_ret"].fillna(0.0)
        return (a.astype(float) + b.astype(float) * x).to_numpy(dtype=float)


# ---------------------------------------------------------------- linear models (M1)
class Winsoriser(BaseEstimator, TransformerMixin):  # type: ignore[misc]
    """Clip each column to its training 1st and 99th percentiles (fitted in-fold, rule L4)."""

    def __init__(self, lower: float = 0.01, upper: float = 0.99) -> None:
        self.lower = lower
        self.upper = upper

    def fit(self, X: Any, y: Any = None) -> Winsoriser:
        values = np.asarray(X, dtype=float)
        with warnings.catch_warnings():
            # A column with no values in this fold (NASI before 2008, say) stays empty; the
            # imputer after this step fills it.
            warnings.simplefilter("ignore", RuntimeWarning)
            self.low_ = np.nanquantile(values, self.lower, axis=0)
            self.high_ = np.nanquantile(values, self.upper, axis=0)
        return self

    def transform(self, X: Any) -> np.ndarray:
        values = np.asarray(X, dtype=float)
        return np.clip(values, self.low_, self.high_)


def linear_pipeline(estimator: Any, numeric: list[str], categorical: list[str]) -> Pipeline:
    numeric_steps = Pipeline(
        [
            ("winsorise", Winsoriser()),
            ("impute", SimpleImputer(strategy="median", keep_empty_features=True)),
            ("scale", StandardScaler()),
        ]
    )
    categorical_steps = Pipeline(
        [
            (
                "impute",
                SimpleImputer(strategy="constant", fill_value=-1.0, keep_empty_features=True),
            ),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ]
    )
    columns = ColumnTransformer(
        [("numeric", numeric_steps, numeric), ("categorical", categorical_steps, categorical)],
        sparse_threshold=0.0,
    )
    return Pipeline([("columns", columns), ("model", estimator)])


@dataclass
class RidgeModel(Forecaster):
    name: ClassVar[str] = "ridge"
    family: ClassVar[str] = "linear"
    pipeline: Any = None

    def _estimator(self) -> Any:
        return Ridge(alpha=float(self.params.get("alpha", 1.0)))

    def fit(self, train: pd.DataFrame) -> RidgeModel:
        numeric = [f for f in self.features if f not in self.categorical]
        self.pipeline = linear_pipeline(self._estimator(), numeric, list(self.categorical))
        self.pipeline.fit(train[self.features], train["y"].to_numpy(dtype=float))
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.pipeline.predict(test[self.features]), dtype=float)


@dataclass
class HuberModel(RidgeModel):
    """The Huber variant of M1: robust loss, closer to a conditional median."""

    name: ClassVar[str] = "huber"

    def _estimator(self) -> Any:
        return HuberRegressor(
            alpha=float(self.params.get("alpha", 1e-4)),
            epsilon=float(self.params.get("epsilon", 1.35)),
            max_iter=int(self.params.get("max_iter", 500)),
        )


# ---------------------------------------------------------------- trees (M2, M3)
def _split_for_early_stopping(
    train: pd.DataFrame, share: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The last ``share`` of sessions in the training window validates early stopping."""
    dates = np.sort(train["session_date"].unique())
    cut = dates[int(len(dates) * (1 - share))] if len(dates) > 10 else dates[-1]
    return train[train["session_date"] < cut], train[train["session_date"] >= cut]


@dataclass
class LightGBMModel(Forecaster):
    name: ClassVar[str] = "lightgbm"
    family: ClassVar[str] = "lightgbm"
    early_stopping_share: float = 0.10
    booster: Any = None

    def fit(self, train: pd.DataFrame) -> LightGBMModel:
        try:
            import lightgbm as lgb
        except (ImportError, OSError) as exc:  # e.g. a missing OpenMP runtime on macOS
            raise ModelUnavailable(f"LightGBM cannot be loaded: {exc}") from exc
        params = dict(self.params)
        n_estimators = int(params.pop("n_estimators", 1000))
        rounds = int(params.pop("early_stopping_rounds", 50))
        objective = params.pop("objective", "l1")
        huber_delta = float(params.pop("huber_delta", 0.02))
        fit_part, valid_part = _split_for_early_stopping(train, self.early_stopping_share)
        model = lgb.LGBMRegressor(
            objective=objective,
            n_estimators=n_estimators,
            random_state=self.seed,
            n_jobs=self.threads,
            deterministic=True,
            force_col_wise=True,
            verbose=-1,
            alpha=huber_delta if objective == "huber" else 0.9,
            **params,
        )
        validation = (valid_part[self.features], valid_part["y"].to_numpy(dtype=float))
        # LightGBM 4.6 renamed eval_set to eval_X / eval_y; support both.
        if "eval_X" in inspect.signature(model.fit).parameters:
            evaluation: dict[str, Any] = {"eval_X": (validation[0],), "eval_y": (validation[1],)}
        else:  # pragma: no cover - older LightGBM
            evaluation = {"eval_set": [validation]}
        model.fit(
            fit_part[self.features],
            fit_part["y"].to_numpy(dtype=float),
            eval_metric="l1",
            categorical_feature=[c for c in self.categorical if c in self.features],
            callbacks=[lgb.early_stopping(rounds, verbose=False)],
            **evaluation,
        )
        self.booster = model
        self.fit_info = {"best_iteration": int(model.best_iteration_ or n_estimators)}
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        return np.asarray(
            self.booster.predict(
                test[self.features], num_iteration=self.fit_info.get("best_iteration")
            ),
            dtype=float,
        )


@dataclass
class CatBoostModel(Forecaster):
    name: ClassVar[str] = "catboost"
    family: ClassVar[str] = "catboost"
    early_stopping_share: float = 0.10
    booster: Any = None

    def fit(self, train: pd.DataFrame) -> CatBoostModel:
        try:
            from catboost import CatBoostRegressor
        except (ImportError, OSError) as exc:
            raise ModelUnavailable(
                "CatBoost is not installed: run with `uv run --extra full nsefc run --profile full`"
            ) from exc
        params = dict(self.params)
        rounds = int(params.pop("early_stopping_rounds", 50))
        loss = params.pop("loss_function", "MAE")
        if loss == "Huber":
            loss = "Huber:delta=0.02"
        fit_part, valid_part = _split_for_early_stopping(train, self.early_stopping_share)
        model = CatBoostRegressor(
            loss_function=loss,
            random_seed=self.seed,
            thread_count=self.threads,
            allow_writing_files=False,
            verbose=False,
            **params,
        )
        model.fit(
            fit_part[self.features],
            fit_part["y"].to_numpy(dtype=float),
            eval_set=(valid_part[self.features], valid_part["y"].to_numpy(dtype=float)),
            early_stopping_rounds=rounds,
        )
        self.booster = model
        self.fit_info = {"best_iteration": int(model.get_best_iteration() or 0)}
        return self

    def predict(self, test: pd.DataFrame) -> np.ndarray:
        return np.asarray(self.booster.predict(test[self.features]), dtype=float)


BASELINES: dict[str, type[Forecaster]] = {
    "B0": NoChange,
    "B1": Drift,
    "B2": MovingAverage,
    "B3": AR1,
}
CANDIDATES: dict[str, type[Forecaster]] = {
    "ridge": RidgeModel,
    "huber": HuberModel,
    "lightgbm": LightGBMModel,
    "catboost": CatBoostModel,
}


def family_rank(model_id: str) -> int:
    """Simpler first: baseline < linear < LightGBM < CatBoost (tie-break order, §11.5)."""
    if model_id in BASELINES:
        return FAMILY_ORDER["baseline"]
    return FAMILY_ORDER[CANDIDATES[model_id].family]
