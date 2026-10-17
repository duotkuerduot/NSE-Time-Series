"""Gates and champion selection (§11.4, §11.5)."""

from nsefc.selection.gates import (
    GATE_ORDER,
    SIMPLE_BASELINES,
    Assessment,
    Choice,
    Gate,
    PlausibilityError,
    choose_champion,
    evaluate_gates,
    plausibility,
)

__all__ = [
    "GATE_ORDER",
    "SIMPLE_BASELINES",
    "Assessment",
    "Choice",
    "Gate",
    "PlausibilityError",
    "choose_champion",
    "evaluate_gates",
    "plausibility",
]
