from __future__ import annotations

import json
import shutil
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from nsefc.api import v1
from nsefc.api.export import resource_for, schema_documents, stale_schemas, validate_tree


@pytest.fixture
def fixtures(repo_root: Path) -> Path:
    return repo_root / "contracts" / "api" / "v1" / "fixtures"


def test_fixtures_are_valid(fixtures: Path) -> None:
    assert validate_tree(fixtures) == []


def test_committed_schemas_are_current(repo_root: Path) -> None:
    assert stale_schemas(repo_root / "contracts" / "api" / "v1") == []


def test_every_resource_has_a_fixture(fixtures: Path) -> None:
    seen = {resource_for(p.relative_to(fixtures).as_posix()) for p in fixtures.rglob("*.json")}
    assert set(v1.RESOURCES.values()) <= seen


@pytest.mark.parametrize(
    ("path", "model"),
    [
        ("status.json", v1.Status),
        ("r/2026-10-07.4f9c2a1/stocks.json", v1.StocksIndex),
        ("r/2026-10-07.4f9c2a1/stocks/SCOM.json", v1.StockDetail),
        ("r/2026-10-07.4f9c2a1/stocks/SCOM/history.1y.json", v1.PriceHistory),
        ("r/2026-10-07.4f9c2a1/stocks/SCOM/history.max.json", v1.PriceHistory),
        ("r/2026-10-07.4f9c2a1/stocks/SCOM/prediction.json", v1.StockPrediction),
        ("r/2026-10-07.4f9c2a1/market/overview.json", v1.MarketOverview),
        ("r/2026-10-07.4f9c2a1/stocks/SCOM/history.5y.json", None),
        ("r/latest/stocks.json", None),
    ],
)
def test_resource_paths(path: str, model: type | None) -> None:
    assert resource_for(path) is model


def test_schemas_carry_ids() -> None:
    documents = schema_documents()
    assert set(documents) == set(v1.RESOURCES)
    assert all(doc["$id"].endswith(f"{name}.schema.json") for name, doc in documents.items())


def load(fixtures: Path, pattern: str) -> dict:  # type: ignore[type-arg]
    (path,) = list(fixtures.glob(pattern))
    return json.loads(path.read_text())


def test_prediction_needs_exactly_one_of_latest_or_reason(fixtures: Path) -> None:
    data = load(fixtures, "r/*/stocks/SCOM/prediction.json")
    data["unavailable_reason"] = "DATA_QUALITY_HOLD"
    with pytest.raises(ValidationError, match="exactly one"):
        v1.StockPrediction.model_validate(data)
    data["latest"] = None
    assert v1.StockPrediction.model_validate(data).latest is None


def test_forecast_must_sit_inside_its_range(fixtures: Path) -> None:
    data = load(fixtures, "r/*/stocks/SCOM/prediction.json")
    data["latest"]["range"]["upper"] = data["latest"]["predicted_close"] - 0.5
    with pytest.raises(ValidationError, match="range"):
        v1.StockPrediction.model_validate(data)


def test_history_series_must_align(fixtures: Path) -> None:
    data = load(fixtures, "r/*/stocks/SCOM/history.1y.json")
    data["close"] = data["close"][:-1]
    with pytest.raises(ValidationError, match="lengths"):
        v1.PriceHistory.model_validate(data)


def test_unknown_fields_are_rejected(fixtures: Path) -> None:
    data = load(fixtures, "r/*/stocks/SCOM.json")
    data["target_price"] = 30.0
    with pytest.raises(ValidationError):
        v1.StockDetail.model_validate(data)


def test_status_must_point_at_a_present_release(fixtures: Path, tmp_path: Path) -> None:
    copy = tmp_path / "v1"
    shutil.copytree(fixtures, copy)
    status = json.loads((copy / "status.json").read_text())
    status["release_id"] = "2026-10-08.abcdef1"
    (copy / "status.json").write_text(json.dumps(status))
    assert any("not present" in p for p in validate_tree(copy))


def test_status_session_order() -> None:
    with pytest.raises(ValidationError):
        v1.Status.model_validate(
            {
                "release_id": "2026-10-07.4f9c2a1",
                "generated_at": "2026-10-07T15:48:12Z",
                "latest_session": date(2026, 10, 7),
                "next_session": date(2026, 10, 7),
                "stale_after": "2026-10-08T19:00:00Z",
                "pipeline": {
                    "status": "succeeded",
                    "finished_at": None,
                    "primary_source": None,
                    "fallback_used": False,
                    "dq": "passed",
                },
                "champion": None,
            }
        )


def test_timestamps_need_an_offset(fixtures: Path) -> None:
    data = load(fixtures, "status.json")
    data["stale_after"] = "2026-10-08T22:00:00"
    with pytest.raises(ValidationError, match="timezone"):
        v1.Status.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"), [("range_coverage", 1.7), ("mae_pct", -0.5), ("directional_accuracy", -0.1)]
)
def test_track_record_rates_are_bounded(fixtures: Path, field: str, value: float) -> None:
    data = load(fixtures, "r/*/stocks/SCOM/prediction.json")
    data["track_record"][field] = value
    with pytest.raises(ValidationError):
        v1.StockPrediction.model_validate(data)


def test_history_range_must_match_its_file_name(fixtures: Path, tmp_path: Path) -> None:
    copy = tmp_path / "v1"
    shutil.copytree(fixtures, copy)
    (path,) = list(copy.glob("r/*/stocks/SCOM/history.1y.json"))
    body = json.loads(path.read_text())
    body["range"] = "max"
    path.write_text(json.dumps(body))
    assert any("does not match the name" in p for p in validate_tree(copy))


@pytest.mark.parametrize(
    ("last", "predicted", "ret", "ok"),
    [
        (390.0, 393.17, 0.0081, True),  # return rounded to 4 places: implied 393.159
        (525.0, 529.61, 0.0088, True),
        (28.45, 28.61, 0.0056, True),
        (390.0, 395.00, 0.0081, False),  # off by KES 1.84: not a rounding difference
    ],
)
def test_forecast_consistency_allows_rounding(
    fixtures: Path, last: float, predicted: float, ret: float, ok: bool
) -> None:
    data = load(fixtures, "r/*/stocks/SCOM/prediction.json")
    latest = data["latest"]
    latest.update(last_close=last, predicted_close=predicted, predicted_return=ret)
    latest["range"].update(lower=round(predicted * 0.97, 2), upper=round(predicted * 1.03, 2))
    if ok:
        v1.StockPrediction.model_validate(data)
    else:
        with pytest.raises(ValidationError, match="last_close"):
            v1.StockPrediction.model_validate(data)
