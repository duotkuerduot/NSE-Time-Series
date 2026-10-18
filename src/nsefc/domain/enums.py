"""Closed sets shared across modules. Values are the strings stored in files and the API."""

from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    """Data-quality severities: error blocks the run, exclude drops rows from modelling."""

    ERROR = "error"
    EXCLUDE = "exclude"
    WARN = "warn"
    INFO = "info"


class UnavailableReason(StrEnum):
    """Why a security has no forecast in a release (API contract v1)."""

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
    """Where raw files came from: the manifest's ``source`` field."""

    MENDELEY = "mendeley"
    LOCAL = "local"
    SAMPLE = "sample"
    USER_IMPORT = "user_import"


class InstrumentType(StrEnum):
    """Only ordinary shares enter the forecast universe."""

    ORDINARY = "ordinary"
    PREFERENCE = "preference"
    RIGHTS = "rights"
    ETF = "etf"
    REIT = "reit"
    INDEX = "index"
