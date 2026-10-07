from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest

from nsefc.domain import (
    CorporateAction,
    CorporateActionType,
    DailyBar,
    DomainError,
    Prediction,
    PredictionRole,
    PredictionSupersession,
    SecuritySymbol,
    SessionIngestStatus,
)


def bar(**overrides: object) -> DailyBar:
    values: dict[str, object] = {
        "security_id": 1,
        "session_date": date(2026, 10, 7),
        "close": 28.45,
        "volume": 9_184_200,
        "provider_id": "test",
        "high": 28.9,
        "low": 28.1,
    }
    values.update(overrides)
    return DailyBar(**values)  # type: ignore[arg-type]


def test_valid_bar() -> None:
    b = bar()
    assert b.traded and b.price_set


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"close": 0.0}, "close"),
        ({"close": float("nan")}, "close"),
        ({"volume": -1}, "volume"),
        ({"high": 27.0, "low": 28.0}, "high"),
        ({"session_date": datetime(2026, 10, 7, tzinfo=UTC)}, "session_date"),
        ({"is_carried_forward": True}, "carried-forward"),
    ],
)
def test_bar_invariants(overrides: dict[str, object], message: str) -> None:
    with pytest.raises(DomainError, match=message):
        bar(**overrides)


def test_price_set_needs_100_shares() -> None:
    # NSE Equity Trading Rules 7.6.6: under 100 shares the previous average price stands.
    assert bar(volume=99).traded and not bar(volume=99).price_set
    assert bar(volume=100).price_set
    untraded = bar(volume=0, is_carried_forward=True, high=None, low=None)
    assert not untraded.traded and not untraded.price_set


def test_symbol_validity_interval() -> None:
    symbol = SecuritySymbol(1, "ABSA", date(2019, 7, 1))
    assert symbol.is_valid_on(date(2026, 1, 1)) and not symbol.is_valid_on(date(2019, 6, 30))
    with pytest.raises(DomainError):
        SecuritySymbol(1, "BBK", date(2019, 7, 1), date(2019, 1, 1))


def test_corporate_action_rules() -> None:
    CorporateAction(
        1, 1, CorporateActionType.DIVIDEND, date(2026, 6, 10), "notice", cash_amount=1.2
    )
    with pytest.raises(DomainError):
        CorporateAction(2, 1, CorporateActionType.BONUS, date(2026, 6, 10), "notice")


def prediction(**overrides: object) -> Prediction:
    values: dict[str, object] = {
        "prediction_id": "p1",
        "model_id": "m_naive",
        "security_id": 1,
        "origin_session": date(2026, 10, 7),
        "target_session_expected": date(2026, 10, 8),
        "role": PredictionRole.CHAMPION,
        "last_close": 28.45,
        "predicted_return": 0.0,
        "predicted_close": 28.45,
        "lower": 27.9,
        "upper": 29.0,
        "generated_at": datetime(2026, 10, 7, 15, 47, tzinfo=UTC),
        "feature_snapshot_sha256": "0" * 64,
        "calibration_id": "c1",
        "pipeline_run_id": "r1",
    }
    values.update(overrides)
    return Prediction(**values)  # type: ignore[arg-type]


def test_prediction_valid_and_append_only_fields() -> None:
    p = prediction()
    assert p.revision == 0 and p.horizon_sessions == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"lower": 28.5},
        {"predicted_return": 0.01},
        {"target_session_expected": date(2026, 10, 7)},
        {"generated_at": datetime(2026, 10, 7, 18, 47)},
        {"generated_at": datetime(2026, 10, 7, 18, 47, tzinfo=timezone(timedelta(hours=3)))},
    ],
)
def test_prediction_invariants(overrides: dict[str, object]) -> None:
    with pytest.raises(DomainError):
        prediction(**overrides)


def test_supersession_needs_reason() -> None:
    with pytest.raises(DomainError):
        PredictionSupersession("p1", "p2", "  ")


def test_resolved_states() -> None:
    assert SessionIngestStatus.MISSING_ACKNOWLEDGED.is_resolved
    assert not SessionIngestStatus.MISSING.is_resolved
