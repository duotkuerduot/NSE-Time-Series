"""Maintainer tools: the web build hash (§15.4) and the README results block (§18)."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

WEB_INPUTS = ("web/index.html", "web/package.json", "web/pnpm-lock.yaml", "web/vite.config.ts")
HASH_FILE = "src/nsefc/web_dist/.source-hash"
START, END = "<!-- results:start -->", "<!-- results:end -->"


def web_source_files(root: Path) -> list[str]:
    """``web/src/**`` sorted by POSIX path, then the build inputs (web/scripts/source-hash.mjs
    computes the same list, so the build and this check agree)."""
    sources = sorted(
        p.relative_to(root).as_posix() for p in (root / "web" / "src").rglob("*") if p.is_file()
    )
    return sources + [name for name in WEB_INPUTS if (root / name).is_file()]


def web_source_hash(root: Path) -> str:
    """SHA-256 over the frontend's sources, independent of the platform's line endings."""
    digest = hashlib.sha256()
    for relative in web_source_files(root):
        digest.update(relative.encode("utf-8") + b"\x00")
        digest.update(
            root.joinpath(*relative.split("/")).read_bytes().replace(b"\r\n", b"\n") + b"\x00"
        )
    return digest.hexdigest()


def committed_web_hash(root: Path) -> str | None:
    path = root / HASH_FILE
    return path.read_text(encoding="utf-8").strip() if path.is_file() else None


def _pct(value: Any, digits: int = 1, signed: bool = True) -> str:
    if not isinstance(value, int | float) or not math.isfinite(value):
        return "n/a"
    return f"{value:+.{digits}%}" if signed else f"{value:.{digits}%}"


def results_block(evaluation: dict[str, Any], ingest: dict[str, Any]) -> str:
    """The README's results section (§18 item 3), from the latest maintainer run."""
    champion = evaluation["champion"]
    models = {m["model_id"]: m for m in evaluation["models"]}
    hold_start, hold_end = evaluation["periods"]["holdout"]
    dataset = ingest.get("dataset", {})
    universe = evaluation.get("universe", {})
    lines = [
        f"From `uv run nsefc run` on {dataset.get('title', 'the dataset')} "
        f"({ingest['first_session']} to {ingest['last_session']}), default profile. Choices "
        f"used the selection period ({evaluation['periods']['selection'][0]} to "
        f"{evaluation['periods']['selection'][1]}); the holdout ({hold_start} to {hold_end}) "
        "was never used to choose anything.",
        "",
    ]
    champ = models[champion["model_id"]]
    hold = champ.get("holdout") or {}
    stocks = (
        f"{universe['min']} to {universe['max']} liquid NSE stocks (median {universe['median']})"
        if universe
        else "the liquid NSE stocks"
    )
    if champion["model_id"] != "B0" and hold:
        lines += [
            f"**Champion: {champion['label']}.** {champion['reason']}. On the holdout its "
            f"average miss was {_pct(hold['mae'], 2, False)} of the price, against "
            f"{_pct(hold['mae_b0'], 2, False)} for a no-change guess (skill "
            f"{_pct(hold['skill'], 2)}, DM p = {hold['dm_p']:.3f}), across {stocks}. The actual "
            f"close fell inside its 80% range {_pct(hold['coverage'], 1, False)} of the time.",
            "",
        ]
    else:
        lines.append(
            "**Champion: the no-change guess.** No model beat it by the margins the gates "
            "require, so the app shows the no-change guess and says so. On this data that is "
            "the honest result."
        )
        ml = [m for m in evaluation["models"] if not m["model_id"].startswith("B")]
        best = max(ml, key=lambda m: m["selection"]["skill"], default=None)
        if best is not None:
            sel, h = best["selection"], best.get("holdout") or {}
            lines[-1] += (
                f" The strongest machine-learning model, {best['label']}, reduced the average miss "
                f"by {_pct(sel['skill'], 2, False)} in the selection period (DM p = "
                f"{sel['dm_p']:.3f}) and {_pct(h.get('skill'), 2, False)} on the holdout, "
                "short of the 1% the gates ask for."
            )
        if hold.get("coverage") is not None:
            lines[-1] += (
                f" The 80% range contained the actual close {_pct(hold['coverage'], 1, False)} "
                f"of the time on the holdout, across {stocks}."
            )
        lines.append("")
    lines += [
        "| Model | Selection skill | DM p | Holdout skill | 80% range coverage | Gates (§11.4) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for m in evaluation["models"]:
        sel = m["selection"]
        h = m.get("holdout") or {}
        failed = [g["id"] for g in m["gates"] if not g["passed"]]
        gates = (
            "reference"
            if not m["gates"]
            else ("all passed" if not failed else "failed " + ", ".join(failed))
        )
        lines.append(
            f"| {m['label']} | {_pct(sel['skill'], 2)} | {sel['dm_p']:.3f} | "
            f"{_pct(h.get('skill'), 2)} | "
            f"{_pct(sel['coverage'], 1, False)} | {gates} |"
        )
    lines += [
        "",
        "Skill is 1 - (model's average miss / no-change guess's average miss): positive means the "
        'model missed by less. It is never an "accuracy" percentage of the price. Coverage is for '
        "the selection period; the gates are defined in [ENGINEERING.md](ENGINEERING.md) §11.4.",
    ]
    return "\n".join(lines)


def update_readme(readme: Path, block: str) -> bool:
    """Replace the text between the results markers; returns whether the file changed."""
    text = readme.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise ValueError(f"{readme} has no {START} ... {END} markers")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    updated = f"{head}{START}\n{block}\n{END}{tail}"
    if updated == text:
        return False
    readme.write_text(updated, encoding="utf-8")
    return True
