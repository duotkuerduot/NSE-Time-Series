"""Closed sets shared across modules. Values are the strings stored in the database and API."""

from __future__ import annotations

from enum import StrEnum


class PriceBasis(StrEnum):
    """How a provider defines the daily price (ENGINEERING.md 7.2, check PRV-02)."""

    VWAP = "vwap"  # NSE official price: VWAP of the whole session (Equity Trading Rules 7.6.1)
    LAST = "last"  # last traded price
    UNKNOWN = "unknown"


class Severity(StrEnum):
    """Data-quality severities (§6.6): error blocks the run, exclude drops rows from modelling."""

    ERROR = "error"
    EXCLUDE = "exclude"
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
    RECENT_PRICE_EVENT = "RECENT_PRICE_EVENT"  # a band-breaching move inside the gap-guard window


class DirectionOutcome(StrEnum):
    HIT = "hit"
    MISS = "miss"
    NO_CHANGE = "no_change"


class DataMode(StrEnum):
    """What the published results are built from (status.json, contract v1.1)."""

    HISTORICAL = "historical"
    HISTORICAL_WITH_IMPORTS = "historical+imports"
    SAMPLE = "sample"


class SourceKind(StrEnum):
    """Where raw files came from (§5): the manifest's ``source`` field."""

    MENDELEY = "mendeley"
    LOCAL = "local"
    SAMPLE = "sample"
    USER_IMPORT = "user_import"


class InstrumentType(StrEnum):
    """Only ordinary shares enter the forecast universe (§6.5, §13.1)."""

    ORDINARY = "ordinary"
    PREFERENCE = "preference"
    RIGHTS = "rights"
    ETF = "etf"
    REIT = "reit"
    INDEX = "index"


class SessionStatus(StrEnum):
    """A weekday in ``sessions.parquet`` (§6.1, §7)."""

    HELD = "held"
    MISSING = "missing"
    HOLIDAY = "holiday"
