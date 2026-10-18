"""Closed sets of values shared across the stages. No I/O, and no imports from the rest of
nsefc."""

from nsefc.domain.enums import (
    DataMode,
    DirectionOutcome,
    InstrumentType,
    Severity,
    SourceKind,
    UnavailableReason,
)

__all__ = [
    "DataMode",
    "DirectionOutcome",
    "InstrumentType",
    "Severity",
    "SourceKind",
    "UnavailableReason",
]
