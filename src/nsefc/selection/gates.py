"""Gates and champion selection (§11.4, §11.5). Thresholds are fixed before results are seen.

A model's *selection* metrics decide every gate except G-HOLD, which uses the holdout only to
confirm. G-PLAUS stops the run: results far better than plausible are treated as a leakage
bug, whatever the other gates say.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nsefc.config import GateSettings
from nsefc.evaluation import PeriodMetrics

SIMPLE_BASELINES = ("B1", "B2", "B3")
GATE_ORDER = ("G-INT", "G-SKILL", "G-BASE", "G-STAB", "G-DIR", "G-CAL", "G-HOLD")
# Plain-language names for reports and the About page (the app never shows the raw ids).
GATE_NAMES = {
    "G-INT": "Integrity checks",
    "G-SKILL": "Beats the no-change guess",
    "G-BASE": "Beats the simple baselines",
    "G-STAB": "Stable from year to year",
    "G-DIR": "Direction no worse than simple rules",
    "G-CAL": "80% range is calibrated",
    "G-HOLD": "Confirmed on the holdout period",
}


class PlausibilityError(RuntimeError):
    """G-PLAUS fired: suspected leakage (exit code 30)."""


@dataclass(slots=True)
class Gate:
    id: str
    passed: bool
    detail: str

    @property
    def name(self) -> str:
        return GATE_NAMES.get(self.id, self.id)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass(slots=True)
class Assessment:
    model_id: str
    label: str
    family_rank: int
    selection: PeriodMetrics
    holdout: PeriodMetrics | None
    gates: dict[str, Gate] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def is_baseline(self) -> bool:
        return self.model_id.startswith("B")

    def passes(self, *ids: str) -> bool:
        return all(self.gates[g].passed for g in (ids or GATE_ORDER) if g in self.gates)


def _pct(value: float) -> str:
    return "n/a" if not math.isfinite(value) else f"{value:+.2%}"


def plausibility(assessments: list[Assessment], gates: GateSettings) -> list[str]:
    """Reasons to suspect leakage (G-PLAUS); empty when every model looks plausible."""
    reasons = []
    for a in assessments:
        for name, period in (("selection", a.selection), ("holdout", a.holdout)):
            if period is None:
                continue
            if math.isfinite(period.skill) and period.skill > gates.plaus_skill_max:
                reasons.append(
                    f"{a.model_id} {name} skill {period.skill:.1%} > {gates.plaus_skill_max:.0%}"
                )
            accuracy = period.direction.accuracy
            if math.isfinite(accuracy) and accuracy > gates.plaus_direction_max:
                reasons.append(
                    f"{a.model_id} {name} directional accuracy {accuracy:.1%} > "
                    f"{gates.plaus_direction_max:.0%}"
                )
    return reasons


def evaluate_gates(
    assessments: list[Assessment],
    gates: GateSettings,
    *,
    integrity: dict[str, tuple[bool, str]],
    paired_p: Callable[[str, str], float],
) -> None:
    """Fill ``gates`` on every assessment except the B0 reference."""
    by_id = {a.model_id: a for a in assessments}
    simple = [by_id[b] for b in SIMPLE_BASELINES if b in by_id]
    best_simple = min(simple, key=lambda a: a.selection.mae) if simple else None
    for a in assessments:
        if a.model_id == "B0":
            a.notes.append("Reference: every skill is measured against this no-change guess.")
            continue
        sel, hold = a.selection, a.holdout
        ok, detail = integrity.get(a.model_id, (True, "no artifact (closed-form baseline)"))
        a.gates["G-INT"] = Gate("G-INT", ok, detail)
        a.gates["G-SKILL"] = Gate(
            "G-SKILL",
            sel.skill >= gates.skill_min and sel.dm_p < gates.skill_p_max,
            f"skill {_pct(sel.skill)} (needs >= {gates.skill_min:.0%}), DM p = {sel.dm_p:.3f} "
            f"(needs < {gates.skill_p_max})",
        )
        if best_simple is None or a is best_simple:
            a.gates["G-BASE"] = Gate("G-BASE", True, "best simple baseline")
        else:
            no_worse = sel.mae <= best_simple.selection.mae
            p = paired_p(a.model_id, best_simple.model_id) if not a.is_baseline else float("nan")
            if a.is_baseline:
                a.gates["G-BASE"] = Gate(
                    "G-BASE", False, f"{best_simple.model_id} has the lower MAE"
                )
            elif not no_worse:
                a.gates["G-BASE"] = Gate("G-BASE", False, f"MAE above {best_simple.model_id}")
            elif not p < gates.base_p_max:
                a.gates["G-BASE"] = Gate(
                    "G-BASE",
                    False,
                    f"not significantly better than {best_simple.model_id} (p = {p:.3f}); "
                    "the simpler model wins",
                )
            else:
                a.gates["G-BASE"] = Gate(
                    "G-BASE", True, f"beats {best_simple.model_id} (p = {p:.3f})"
                )
        years = sel.skill_by_year
        needed = math.ceil(gates.stab_min_positive_share * len(years)) if years else 0
        positive = sum(1 for v in years.values() if v > 0)
        worst = min(years.values()) if years else float("nan")
        a.gates["G-STAB"] = Gate(
            "G-STAB",
            bool(years) and positive >= needed and worst >= gates.stab_year_floor,
            f"positive in {positive} of {len(years)} years (needs {needed}); "
            f"worst year {_pct(worst)}",
        )
        worse = sel.direction.worse_than_trivial(gates.dir_alpha)
        a.gates["G-DIR"] = Gate(
            "G-DIR",
            not worse,
            f"{sel.direction.accuracy:.1%} vs best trivial {sel.direction.best_trivial:.1%} "
            f"on {sel.direction.n:,} calls"
            if sel.direction.n
            else "makes no directional calls",
        )
        a.gates["G-CAL"] = Gate(
            "G-CAL",
            gates.cal_low <= sel.coverage <= gates.cal_high,
            f"80% range contained the actual close {sel.coverage:.1%} of the time "
            f"(needs {gates.cal_low:.0%} to {gates.cal_high:.0%})",
        )
        if hold is None:
            a.gates["G-HOLD"] = Gate("G-HOLD", False, "no holdout predictions")
        else:
            a.gates["G-HOLD"] = Gate(
                "G-HOLD",
                hold.skill > 0 and hold.skill >= gates.hold_min_ratio * sel.skill,
                f"holdout skill {_pct(hold.skill)} vs selection {_pct(sel.skill)}",
            )


@dataclass(slots=True)
class Choice:
    champion: str
    reason: str


def choose_champion(
    assessments: list[Assessment],
    gates: GateSettings,
    *,
    paired_p: Callable[[str, str], float],
) -> Choice:
    """§11.5: the best gated ML candidate; else the best gated simple baseline; else B0."""
    candidates = [a for a in assessments if not a.is_baseline and a.passes()]
    if candidates:
        candidates.sort(key=lambda a: a.selection.mae)
        best = candidates[0]
        simpler = [
            c
            for c in candidates[1:]
            if c.family_rank < best.family_rank
            and not paired_p(best.model_id, c.model_id) < gates.base_p_max
        ]
        if simpler:
            chosen = min(simpler, key=lambda c: (c.family_rank, c.selection.mae))
            return Choice(
                chosen.model_id,
                f"{chosen.label} passed every gate and {best.label} was not significantly better",
            )
        return Choice(
            best.model_id, f"{best.label} passed every gate with the lowest selection-period miss"
        )
    baselines = [
        a
        for a in assessments
        if a.model_id in SIMPLE_BASELINES and a.passes("G-INT", "G-SKILL", "G-BASE", "G-CAL")
    ]
    if baselines:
        best = min(baselines, key=lambda a: a.selection.mae)
        return Choice(
            best.model_id, f"No ML model passed every gate; {best.label} beat the no-change guess"
        )
    return Choice("B0", "No model beat the no-change guess by enough to pass the gates")
