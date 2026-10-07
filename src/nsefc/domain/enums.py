"""Closed sets shared across modules. Values are the strings stored in the database and API."""

from __future__ import annotations

from enum import StrEnum


class PriceBasis(StrEnum):
    """How a provider defines the daily price (ENGINEERING.md 7.2, check PRV-02)."""

    VWAP = "vwap"  # NSE official price: VWAP of the whole session (Equity Trading Rules 7.6.1)
    LAST = "last"  # last traded price
    UNKNOWN = "unknown"


class Severity(StrEnum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


class CheckScope(StrEnum):
    ROW = "row"
    BATCH = "batch"
    HISTORY = "history"


class SessionIngestStatus(StrEnum):
    """Per-session commit status (table session_ingest).

    MISSING_ACKNOWLEDGED is terminal: an audited command records that no source will ever
    supply the session, so ingestion may move past it (review MF-1). Labels never span it.
    """

    PENDING = "pending"
    COMMITTED = "committed"
    QUARANTINED = "quarantined"
    MISSING = "missing"
    MISSING_ACKNOWLEDGED = "missing_acknowledged"

    @property
    def is_resolved(self) -> bool:
        return self in (SessionIngestStatus.COMMITTED, SessionIngestStatus.MISSING_ACKNOWLEDGED)


class SecurityStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELISTED = "delisted"


class CorporateActionType(StrEnum):
    SPLIT = "split"
    CONSOLIDATION = "consolidation"
    BONUS = "bonus"
    RIGHTS = "rights"
    DIVIDEND = "dividend"


class ModelStatus(StrEnum):
    CANDIDATE = "candidate"
    SHADOW = "shadow"
    CHAMPION = "champion"
    RETIRED = "retired"
    REJECTED = "rejected"


class PredictionRole(StrEnum):
    CHAMPION = "champion"
    SHADOW = "shadow"


class UnavailableReason(StrEnum):
    """Why a security has no forecast in a release (ENGINEERING.md 22.3)."""

    NOT_IN_FORECAST_UNIVERSE = "NOT_IN_FORECAST_UNIVERSE"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    SUSPENDED = "SUSPENDED"
    DATA_QUALITY_HOLD = "DATA_QUALITY_HOLD"
    PIPELINE_DELAYED = "PIPELINE_DELAYED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"


class DirectionOutcome(StrEnum):
    HIT = "hit"
    MISS = "miss"
    NO_CHANGE = "no_change"


class RunType(StrEnum):
    DAILY = "daily"
    REFIT = "refit"
    COMPETITION = "competition"
    BACKFILL = "backfill"
    AUDIT = "audit"
    DRYRUN = "dryrun"
    SPIKE = "spike"


class Environment(StrEnum):
    DEVELOPMENT = "development"
    CI = "ci"
    DRYRUN = "dryrun"
    PRODUCTION = "production"
