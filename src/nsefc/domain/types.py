"""Core value types. Immutable, validated on construction, and free of I/O."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from nsefc.domain.enums import CorporateActionType, PredictionRole, SecurityStatus

EAT = ZoneInfo("Africa/Nairobi")

# NSE Equity Trading Rules (amended July 2025), rule 7.6.6: the closing price is volume
# weighted with a minimum cumulative volume of 100 shares; below that, the previous
# session's average price stands. A session "sets a price" only at or above this volume.
MIN_PRICE_SETTING_VOLUME = 100

# Rule 5.10.1 and 5.10.2: daily movement limit against the previous session's average price.
MAIN_BOARD_PRICE_BAND = 0.10
RECOVERY_BOARD_PRICE_BAND = 0.05


class DomainError(ValueError):
    """A value violates a domain invariant."""


def _require_session_date(value: object, name: str) -> None:
    # Session dates are local NSE dates and are never derived from timestamps (7.4, 7.5).
    if isinstance(value, datetime) or not isinstance(value, date):
        raise DomainError(f"{name} must be a datetime.date, got {type(value).__name__}")


def _require_positive(value: float | None, name: str) -> None:
    if value is not None and (not math.isfinite(value) or value <= 0):
        raise DomainError(f"{name} must be a positive finite number, got {value!r}")


@dataclass(frozen=True, slots=True)
class Security:
    security_id: int
    name: str
    status: SecurityStatus
    isin: str | None = None
    sector: str | None = None
    segment: str | None = None
    listed_on: date | None = None
    delisted_on: date | None = None


@dataclass(frozen=True, slots=True)
class SecuritySymbol:
    """A ticker valid over [valid_from, valid_to]; valid_to None means still current."""

    security_id: int
    ticker: str
    valid_from: date
    valid_to: date | None = None

    def __post_init__(self) -> None:
        if self.valid_to is not None and self.valid_to < self.valid_from:
            raise DomainError(f"{self.ticker}: valid_to {self.valid_to} before {self.valid_from}")

    def is_valid_on(self, day: date) -> bool:
        return self.valid_from <= day and (self.valid_to is None or day <= self.valid_to)


@dataclass(frozen=True, slots=True)
class DailyBar:
    """One canonical (security, session) row (ENGINEERING.md 7.4)."""

    security_id: int
    session_date: date
    close: float
    volume: int
    provider_id: str
    prev_close_reported: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    turnover: float | None = None
    deals: int | None = None
    is_carried_forward: bool = False

    def __post_init__(self) -> None:
        _require_session_date(self.session_date, "session_date")
        _require_positive(self.close, "close")
        for name in ("open", "high", "low", "prev_close_reported"):
            _require_positive(getattr(self, name), name)
        if self.volume < 0:
            raise DomainError(f"volume must be >= 0, got {self.volume}")
        if self.turnover is not None and self.turnover < 0:
            raise DomainError(f"turnover must be >= 0, got {self.turnover}")
        if self.high is not None and self.low is not None and self.high < self.low:
            raise DomainError(f"high {self.high} below low {self.low}")
        if self.is_carried_forward and self.volume != 0:
            raise DomainError("a carried-forward row cannot report volume")

    @property
    def traded(self) -> bool:
        """At least one share changed hands (display semantics)."""
        return self.volume > 0

    @property
    def price_set(self) -> bool:
        """The session set a new official price (rule 7.6.6); use this for modelling."""
        return self.volume >= MIN_PRICE_SETTING_VOLUME


@dataclass(frozen=True, slots=True)
class IndexLevel:
    index_code: str
    session_date: date
    level: float
    provider_id: str

    def __post_init__(self) -> None:
        _require_session_date(self.session_date, "session_date")
        _require_positive(self.level, "level")


@dataclass(frozen=True, slots=True)
class CorporateAction:
    """A recorded corporate action. Adjustment arithmetic lives in nsefc.reference."""

    action_id: int
    security_id: int
    action_type: CorporateActionType
    ex_date: date
    source_ref: str
    ratio: float | None = None
    cash_amount: float | None = None

    def __post_init__(self) -> None:
        _require_session_date(self.ex_date, "ex_date")
        if self.action_type is CorporateActionType.DIVIDEND:
            if self.cash_amount is None or self.cash_amount <= 0:
                raise DomainError("a dividend needs a positive cash_amount")
        elif self.ratio is None or self.ratio <= 0:
            raise DomainError(f"a {self.action_type} needs a positive ratio")


@dataclass(frozen=True, slots=True)
class Prediction:
    """An append-only forecast record (ENGINEERING.md 7.3, 20.3, 21.4).

    A pre-open correction never updates a row: it inserts revision n+1 and a separate
    supersession record (review MF-8).
    """

    prediction_id: str
    model_id: str
    security_id: int
    origin_session: date
    target_session_expected: date
    role: PredictionRole
    last_close: float
    predicted_return: float
    predicted_close: float
    lower: float
    upper: float
    generated_at: datetime
    feature_snapshot_sha256: str
    calibration_id: str
    pipeline_run_id: str
    horizon_sessions: int = 1
    revision: int = 0
    is_late: bool = False

    def __post_init__(self) -> None:
        _require_session_date(self.origin_session, "origin_session")
        _require_session_date(self.target_session_expected, "target_session_expected")
        if self.target_session_expected <= self.origin_session:
            raise DomainError("target session must come after the origin session")
        if self.horizon_sessions < 1:
            raise DomainError("horizon_sessions must be >= 1")
        if self.revision < 0:
            raise DomainError("revision must be >= 0")
        for name in ("last_close", "predicted_close", "lower", "upper"):
            _require_positive(getattr(self, name), name)
        if not self.lower <= self.predicted_close <= self.upper:
            raise DomainError("expected lower <= predicted_close <= upper")
        implied = self.last_close * (1.0 + self.predicted_return)
        if not math.isclose(implied, self.predicted_close, rel_tol=1e-9, abs_tol=1e-9):
            raise DomainError("predicted_close must equal last_close * (1 + predicted_return)")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() != UTC.utcoffset(None):
            raise DomainError("generated_at must be timezone-aware UTC")


@dataclass(frozen=True, slots=True)
class PredictionSupersession:
    """Records that a published prediction was replaced before its target session opened."""

    prediction_id: str
    superseded_by: str
    reason: str
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise DomainError("a supersession needs a reason")
