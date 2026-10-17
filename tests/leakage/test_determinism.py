"""Determinism and artifact integrity (§10.2, §10.3, §16.2)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from nsefc.config import load_settings
from nsefc.evaluation import UniverseRule, build_model_data, training_rows
from nsefc.features import FeatureSpec
from nsefc.models import (
    AR1,
    ArtifactError,
    HuberModel,
    LightGBMModel,
    RidgeModel,
    load_artifact,
    save_artifact,
)
from nsefc.targets import winsorise
from tests.conftest import ROOT, synthetic_market

SPECS = load_settings("test", project_root=ROOT, environ={}).model_specs


@pytest.fixture(scope="module")
def frames(calendar):  # type: ignore[no-untyped-def]
    market = synthetic_market(calendar, tickers=8, sessions=700, phi=0.15, seed=21)
    rule = UniverseRule(
        window=250, min_traded_share=0.8, min_median_turnover_kes=0, min_history=250
    )
    data = build_model_data(market.panel(), FeatureSpec(), rule, sigma_floor=0.0025)
    cut = data.held[600]
    train = training_rows(data.table, cut).sort_values(["session_date", "ticker"], kind="stable")
    train = train.assign(y=winsorise(train["y"].to_numpy(dtype=float), 0.105))
    test = data.table[(data.table["session_date"] >= cut) & data.table["window_ok"]]
    return data, train, test


def models(data):  # type: ignore[no-untyped-def]
    feats, cats = list(data.features), list(data.categorical)
    lgb = {**SPECS["lightgbm"].frozen, "n_estimators": 200, "min_data_in_leaf": 200}
    return {
        "B3": lambda: AR1(window=500),
        "ridge": lambda: RidgeModel(
            params=dict(SPECS["ridge"].frozen), features=feats, categorical=cats
        ),
        "huber": lambda: HuberModel(
            params=dict(SPECS["huber"].frozen), features=feats, categorical=cats
        ),
        "lightgbm": lambda: LightGBMModel(
            params=lgb, features=feats, categorical=cats, seed=7, threads=2
        ),
    }


@pytest.mark.parametrize("model_id", ["B3", "ridge", "huber", "lightgbm"])
def test_same_inputs_and_seed_give_identical_predictions(frames, model_id: str) -> None:  # type: ignore[no-untyped-def]
    data, train, test = frames
    make = models(data)[model_id]
    first = make().fit(train).predict(test)
    second = make().fit(train.copy()).predict(test.copy())
    assert np.array_equal(first, second)
    assert np.isfinite(first).all()


@pytest.mark.parametrize("model_id", ["B3", "ridge", "lightgbm"])
def test_artifact_round_trip_and_tamper(frames, tmp_path: Path, model_id: str) -> None:  # type: ignore[no-untyped-def]
    data, train, test = frames
    model = models(data)[model_id]().fit(train)
    path = tmp_path / f"{model_id}.joblib"
    sidecar = save_artifact(model, path, {"role": "test"})
    assert sidecar["sha256"] and path.with_suffix(".json").is_file()
    reloaded = load_artifact(path)
    assert np.allclose(model.predict(test), reloaded.predict(test), rtol=0, atol=1e-9)
    data_bytes = bytearray(path.read_bytes())
    data_bytes[len(data_bytes) // 2] ^= 0xFF
    path.write_bytes(bytes(data_bytes))
    with pytest.raises(ArtifactError, match="does not match"):
        load_artifact(path)


def test_missing_sidecar_is_refused(frames, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    data, train, _test = frames
    path = tmp_path / "m.joblib"
    save_artifact(models(data)["ridge"]().fit(train), path, {})
    path.with_suffix(".json").unlink()
    with pytest.raises(ArtifactError, match="missing"):
        load_artifact(path)
