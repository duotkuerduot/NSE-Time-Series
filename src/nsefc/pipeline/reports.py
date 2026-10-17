"""Markdown reports: the data audit (§6.4) and the evaluation report (§11.5 step 4)."""

from __future__ import annotations

import math
from typing import Any


def _pct(value: Any, digits: int = 2, signed: bool = True) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "n/a"
    return f"{value:+.{digits}%}" if signed else f"{value:.{digits}%}"


def data_audit_markdown(report: dict[str, Any], *, citation: str | None) -> str:
    counts = report["counts"]
    lines = [
        "# Data audit",
        "",
        f"Data mode: **{report['data_mode']}**. Sessions {report['first_session']} to "
        f"{report['last_session']}.",
    ]
    if citation:
        lines += ["", f"Source: {citation}"]
    lines += [
        "",
        "## Counts",
        "",
        "| Item | Count |",
        "| --- | --- |",
    ]
    labels = {
        "files": "Price files read",
        "source_rows": "Source rows",
        "blank_rows": "Blank lines skipped",
        "rows_corrected": "Rows fixed by corrections",
        "identical_duplicates_dropped": "Identical duplicate rows dropped",
        "securities": "Securities",
        "ordinary_shares": "Ordinary shares",
        "held_sessions": "Held sessions",
        "missing_sessions": "Missing sessions (scheduled, no data)",
        "bars": "Canonical bars",
        "carried_forward_rows": "Carried-forward rows (untraded, no source row)",
        "events": "PRC-01 events (excluded from modelling)",
        "imported_rows": "User-imported rows",
    }
    for key, label in labels.items():
        if key in counts:
            lines.append(f"| {label} | {counts[key]:,} |")
    lines += ["", "## Corrections applied", ""]
    if report["corrections"]:
        lines += ["| Rule | File | Action | Rows | Reason |", "| --- | --- | --- | --- | --- |"]
        for c in report["corrections"]:
            lines.append(
                f"| {c['id']} | `{c['file']}` | {c['action']} | {c['rows']} | {c['reason']} |"
            )
    else:
        lines.append("None applied.")
    if report.get("corrections_not_applicable"):
        lines += [
            "",
            "Rules for files not in this dataset (not applied): "
            + ", ".join(report["corrections_not_applicable"])
            + ".",
        ]
    lines += [
        "",
        "## Checks",
        "",
        "| Check | Severity | Count | Examples |",
        "| --- | --- | --- | --- |",
    ]
    for check in report["checks"]:
        examples = "; ".join(check["examples"][:6])
        note = f" {check['note']}" if check["note"] else ""
        lines.append(
            f"| {check['id']} {check['title']} | {check['severity']} | {check['count']:,} | "
            f"{examples}{note} |"
        )
    return "\n".join(lines) + "\n"


def evaluation_markdown(evaluation: dict[str, Any]) -> str:
    lines = [
        "# Evaluation report",
        "",
        f"Profile **{evaluation['profile']}**, refits **{evaluation['refit']}**. Selection "
        f"{evaluation['periods']['selection'][0]} to {evaluation['periods']['selection'][1]}; "
        f"holdout {evaluation['periods']['holdout'][0]} to {evaluation['periods']['holdout'][1]}.",
        "",
        f"**Champion: {evaluation['champion']['label']}** ({evaluation['champion']['model_id']}). "
        f"{evaluation['champion']['reason']}.",
        "",
        f"Forecast universe: {evaluation['universe']['min']} to {evaluation['universe']['max']} "
        f"securities at refit dates (median {evaluation['universe']['median']}).",
        "",
        "## Gate table (selection period unless stated)",
        "",
        "| Model | MAE | Skill vs no change | DM p | 80% coverage | Direction | Holdout skill "
        "| Gates |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for model in evaluation["models"]:
        sel = model["selection"]
        hold = model.get("holdout") or {}
        gates = model.get("gates") or []
        failed = [g["id"] for g in gates if not g["passed"]]
        gate_text = (
            "reference"
            if not gates
            else ("all passed" if not failed else "failed " + ", ".join(failed))
        )
        direction = sel["direction"]
        lines.append(
            f"| {model['label']} | {_pct(sel['mae'], 3, False)} | {_pct(sel['skill'])} | "
            f"{sel['dm_p']:.3f} | {_pct(sel['coverage'], 1, False)} | "
            f"{_pct(direction['accuracy'], 1, False)} | {_pct(hold.get('skill'))} | {gate_text} |"
        )
    lines += ["", "## Gate details", ""]
    for model in evaluation["models"]:
        if not model.get("gates"):
            continue
        lines.append(f"**{model['label']}**")
        lines.append("")
        for gate in model["gates"]:
            mark = "pass" if gate["passed"] else "FAIL"
            lines.append(f"- {gate['id']} {mark}: {gate['detail']}")
        lines.append("")
    lines += ["## Skill by year (vs no change)", ""]
    years = sorted(
        {y for m in evaluation["models"] for y in m["selection"]["skill_by_year"]}
        | {
            y
            for m in evaluation["models"]
            for y in (m.get("holdout") or {}).get("skill_by_year", {})
        }
    )
    lines.append("| Model | " + " | ".join(years) + " |")
    lines.append("| --- " * (len(years) + 1) + "|")
    for model in evaluation["models"]:
        by_year = {
            **model["selection"]["skill_by_year"],
            **(model.get("holdout") or {}).get("skill_by_year", {}),
        }
        lines.append(
            f"| {model['label']} | " + " | ".join(_pct(by_year.get(y), 1) for y in years) + " |"
        )
    plaus = evaluation.get("plausibility")
    if plaus:
        lines += [
            "",
            "## Plausibility tripwire (G-PLAUS)",
            "",
            f"Not triggered: the highest skill of any model in either period was "
            f"{_pct(plaus['highest_skill'], 1)} (limit {_pct(plaus['skill_max'], 0, False)}), "
            "and the highest "
            f"directional accuracy {_pct(plaus['highest_direction'], 1, False)} "
            f"(limit {_pct(plaus['direction_max'], 0, False)}).",
        ]
    rows = evaluation.get("rows")
    if rows:
        lines += [
            "",
            "## Rows used",
            "",
            f"Of {rows['universe_rows']:,} forecast-universe rows in the walk-forward span, "
            f"{rows['gap_guard_excluded']:,} were excluded by the gap guard (a missing session "
            f"or a PRC-01 event in the 60-session window) and {rows['unlabelled']:,} had no label "
            "(the next "
            "session was an event or followed a missing session).",
        ]
    if evaluation.get("breakdowns"):
        lines += ["", "## Champion breakdowns (holdout)", ""]
        for name, values in evaluation["breakdowns"].items():
            lines.append(f"- {name}: " + ", ".join(f"{k} {_pct(v, 1)}" for k, v in values.items()))
    if evaluation.get("unavailable"):
        lines += ["", "## Models not run", ""]
        lines += [f"- {k}: {v}" for k, v in evaluation["unavailable"].items()]
    return "\n".join(lines) + "\n"
