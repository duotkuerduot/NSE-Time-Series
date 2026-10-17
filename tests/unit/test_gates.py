"""Gates and champion selection (§11.4, §11.5): each gate passes and fails on constructed results."""

from __future__ import annotations

import math

import pytest

from nsefc.config import GateSettings
from nsefc.evaluation import Direction, PeriodMetrics
from nsefc.models import family_rank
from nsefc.selection import Assessment, choose_champion, evaluate_gates, plausibility

GATES = GateSettings()
YEARS = (2018, 2019, 2020, 2021, 2022)


def metrics(
    skill: float = 0.03,
    p: float = 0.001,
    coverage: float = 0.80,
    by_year: tuple[float, ...] = (0.03, 0.02, 0.04, 0.01, 0.03),
    accuracy: float = 0.58,
    trivial: float = 0.55,
    calls: int = 5000,
) -> PeriodMetrics:
    mae_b0 = 0.014
    return PeriodMetrics(
        rows=20000,
        sessions=1200,
        securities=20,
        mae=mae_b0 * (1 - skill),
        mae_b0=mae_b0,
        skill=skill,
        dm_stat=-3.0,
        dm_p=p,
        coverage=coverage,
        width=0.03,
        direction=Direction(accuracy, 0.5, calls, trivial, 1 - trivial, 0.5),
        skill_by_year=dict(zip(YEARS, by_year, strict=True)),
    )


def assess(
    model_id: str, selection: PeriodMetrics, holdout: PeriodMetrics | None = None
) -> Assessment:
    return Assessment(
        model_id,
        model_id,
        family_rank(model_id),
        selection,
        holdout if holdout is not None else metrics(skill=selection.skill * 0.8),
    )


def run(
    assessments: list[Assessment], *, p: float = 0.01, integrity: dict | None = None
) -> dict[str, Assessment]:  # type: ignore[type-arg]
    evaluate_gates(assessments, GATES, integrity=integrity or {}, paired_p=lambda _a, _b: p)
    return {a.model_id: a for a in assessments}


def baselines() -> list[Assessment]:
    return [
        assess("B0", metrics(skill=0.0, p=1.0)),
        assess("B1", metrics(skill=-0.01, p=1.0)),
        assess("B2", metrics(skill=-0.5, p=1.0)),
        assess("B3", metrics(skill=0.005, p=0.2)),
    ]


def test_a_good_candidate_passes_every_gate() -> None:
    result = run([*baselines(), assess("lightgbm", metrics())])
    gates = result["lightgbm"].gates
    assert [g for g, v in gates.items() if not v.passed] == []
    assert result["B0"].gates == {}  # the reference has no gates


@pytest.mark.parametrize(
    ("selection", "holdout", "failed"),
    [
        (metrics(skill=0.008), None, "G-SKILL"),  # skill below 1%
        (metrics(p=0.06), None, "G-SKILL"),  # not significant
        (metrics(by_year=(0.03, -0.01, 0.04, -0.01, 0.03)), None, "G-STAB"),  # 3 of 5 years
        (metrics(by_year=(0.03, 0.02, 0.04, 0.05, -0.03)), None, "G-STAB"),  # a year below -2%
        (metrics(accuracy=0.50, trivial=0.56), None, "G-DIR"),  # worse than trivial
        (metrics(coverage=0.72), None, "G-CAL"),
        (metrics(coverage=0.87), None, "G-CAL"),
        (metrics(), metrics(skill=-0.001), "G-HOLD"),  # holdout not positive
        (metrics(skill=0.04), metrics(skill=0.015), "G-HOLD"),  # under half of selection
    ],
)
def test_each_gate_fails_on_its_own(
    selection: PeriodMetrics, holdout: PeriodMetrics | None, failed: str
) -> None:
    result = run([*baselines(), assess("lightgbm", selection, holdout)])
    gates = result["lightgbm"].gates
    assert [g for g, v in gates.items() if not v.passed] == [failed]


def test_g_base_needs_a_significant_improvement_over_the_best_simple_baseline() -> None:
    result = run([*baselines(), assess("lightgbm", metrics())], p=0.2)
    gate = result["lightgbm"].gates["G-BASE"]
    assert not gate.passed and "simpler model wins" in gate.detail
    worse = run(
        [*baselines()[:3], assess("B3", metrics(skill=0.05)), assess("ridge", metrics(skill=0.03))]
    )
    assert not worse["ridge"].gates["G-BASE"].passed  # MAE above B3's


def test_g_int_reflects_the_artifact_check() -> None:
    result = run(
        [*baselines(), assess("lightgbm", metrics())],
        integrity={"lightgbm": (False, "hash mismatch")},
    )
    assert not result["lightgbm"].gates["G-INT"].passed


def test_no_directional_calls_is_not_a_failure() -> None:
    result = run([*baselines(), assess("lightgbm", metrics(accuracy=math.nan, calls=0))])
    assert result["lightgbm"].gates["G-DIR"].passed


def test_plausibility_tripwire() -> None:
    fine = [*baselines(), assess("lightgbm", metrics())]
    assert plausibility(fine, GATES) == []
    too_good = [*baselines(), assess("lightgbm", metrics(skill=0.2))]
    assert "skill" in plausibility(too_good, GATES)[0]
    too_sure = [*baselines(), assess("lightgbm", metrics(), metrics(accuracy=0.7))]
    assert "lightgbm holdout directional accuracy 70.0% > 65%" in plausibility(too_sure, GATES)


def test_champion_is_the_best_gated_candidate() -> None:
    assessments = [
        *baselines(),
        assess("ridge", metrics(skill=0.025)),
        assess("lightgbm", metrics(skill=0.03)),
    ]
    choice = choose_champion(list(run(assessments).values()), GATES, paired_p=lambda _a, _b: 0.01)
    assert choice.champion == "lightgbm"


def test_ties_go_to_the_simpler_candidate() -> None:
    assessments = [
        *baselines(),
        assess("ridge", metrics(skill=0.025)),
        assess("lightgbm", metrics(skill=0.03)),
    ]
    result = run(assessments)
    choice = choose_champion(list(result.values()), GATES, paired_p=lambda _a, _b: 0.3)
    assert choice.champion == "ridge" and "not significantly better" in choice.reason


def test_fallback_to_the_best_baseline_then_to_no_change() -> None:
    no_ml = [
        *baselines()[:3],
        assess("B3", metrics(skill=0.02)),
        assess("lightgbm", metrics(skill=0.005)),
    ]
    choice = choose_champion(list(run(no_ml).values()), GATES, paired_p=lambda _a, _b: 0.01)
    assert choice.champion == "B3" and "No ML model passed" in choice.reason
    nothing = [*baselines(), assess("lightgbm", metrics(skill=0.002, p=0.3))]
    choice = choose_champion(list(run(nothing).values()), GATES, paired_p=lambda _a, _b: 0.5)
    assert choice.champion == "B0"
    assert choice.reason == "No model beat the no-change guess by enough to pass the gates"


def test_gate_names_are_plain_language() -> None:
    result = run([*baselines(), assess("lightgbm", metrics())])
    names = [g.as_dict()["name"] for g in result["lightgbm"].gates.values()]
    assert "Beats the no-change guess" in names
    assert all(not name.startswith("G-") for name in names)
