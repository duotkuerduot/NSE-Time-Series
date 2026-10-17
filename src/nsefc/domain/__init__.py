"""Core types (Security, Session, Bar, Prediction) and enums. No I/O.

Kept from Phase 0; extended for the local-first tool (ENGINEERING.md 2.0, §4.1).
"""

from nsefc.domain.enums import (
    CheckScope,
    CorporateActionType,
    DataMode,
    DirectionOutcome,
    InstrumentType,
    ModelStatus,
    PredictionRole,
    PriceBasis,
    SecurityStatus,
    SessionIngestStatus,
    SessionStatus,
    Severity,
    SourceKind,
    UnavailableReason,
)
from nsefc.domain.types import (
    EAT,
    MAIN_BOARD_PRICE_BAND,
    MIN_PRICE_SETTING_VOLUME,
    RECOVERY_BOARD_PRICE_BAND,
    CorporateAction,
    DailyBar,
    DomainError,
    IndexLevel,
    Prediction,
    PredictionSupersession,
    Security,
    SecuritySymbol,
)

__all__ = [
    "EAT",
    "MAIN_BOARD_PRICE_BAND",
    "MIN_PRICE_SETTING_VOLUME",
    "RECOVERY_BOARD_PRICE_BAND",
    "CheckScope",
    "CorporateAction",
    "CorporateActionType",
    "DailyBar",
    "DataMode",
    "DirectionOutcome",
    "DomainError",
    "IndexLevel",
    "InstrumentType",
    "ModelStatus",
    "Prediction",
    "PredictionRole",
    "PredictionSupersession",
    "PriceBasis",
    "Security",
    "SecurityStatus",
    "SecuritySymbol",
    "SessionIngestStatus",
    "SessionStatus",
    "Severity",
    "SourceKind",
    "UnavailableReason",
]
