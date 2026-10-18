"""Maintainer tools: the web build hash and the README results block."""

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


def _source_phrase(ingest: dict[str, Any]) -> str:
    dataset = ingest.get("dataset", {})
    if dataset.get("source") == "mendeley":
        return "the NSE daily prices from Mendeley Data"
    if dataset.get("source") == "sample":
        return "the synthetic sample dataset"
    return str(dataset.get("title", "the dataset"))


def _closest(model: dict[str, Any]) -> str:
    """How close the best machine-learning model came, and which gates stopped it."""
    sel, hold = model["selection"], model.get("holdout") or {}
    failed = [
        f"{g['id']} ({g.get('name', g['id']).lower()})" for g in model["gates"] if not g["passed"]
    ]
    text = (
        f" The closest machine-learning model was {model['label']}, with a selection skill of "
        f"{_pct(sel['skill'], 2)} (DM p = {sel['dm_p']:.3f}) and a holdout skill of "
        f"{_pct(hold.get('skill'), 2)}"
    )
    if failed:
        text += ", but it failed " + ", ".join(failed[:-1])
        text += (" and " if len(failed) > 1 else "") + failed[-1]
    return text + "."


def results_block(evaluation: dict[str, Any], ingest: dict[str, Any]) -> str:
    """The README's results section, from the latest maintainer run."""
    champion = evaluation["champion"]
    models = {m["model_id"]: m for m in evaluation["models"]}
    selection = evaluation["periods"]["selection"]
    hold_start, hold_end = evaluation["periods"]["holdout"]
    universe = evaluation.get("universe", {})
    stocks = (
        f"{universe['min']} to {universe['max']} liquid NSE stocks (median {universe['median']})"
        if universe
        else "the liquid NSE stocks"
    )
    lines = [
        f"From `uv run nsefc run` on {_source_phrase(ingest)} ({ingest['first_session']} to "
        f"{ingest['last_session']}), {evaluation.get('profile', 'default')} profile. The models "
        f"are compared on the selection period ({selection[0]} to {selection[1]}); the holdout "
        f"({hold_start} to {hold_end}) only confirms the choice and was never used to make it.",
        "",
    ]
    champ = models[champion["model_id"]]
    hold = champ.get("holdout") or {}
    ml = [m for m in evaluation["models"] if not m["model_id"].startswith("B")]
    best = max(ml, key=lambda m: m["selection"]["skill"], default=None)
    if not champion["model_id"].startswith("B"):
        text = f"**Champion: {champion['label']}.** It passed every gate."
        if hold:
            text += (
                f" On the holdout its average miss was {_pct(hold.get('mae'), 2, False)} of the "
                f"price, against {_pct(hold.get('mae_b0'), 2, False)} for the no-change guess "
                f"(skill {_pct(hold.get('skill'), 2)}, DM p = {hold.get('dm_p', math.nan):.3f})."
            )
    elif champion["model_id"] == "B0":
        text = (
            "**Champion: the no-change guess.** No model beat it by the margins the gates set in "
            "advance, so the framework correctly refused to ship models that did not beat a "
            "strong baseline."
        )
        text += _closest(best) if best is not None else ""
    else:
        text = (
            f"**Champion: the {champion['label']}.** No machine-learning model beat the simple "
            "baselines by the margins the gates set in advance, so the framework correctly "
            f"refused to ship them and chose the {champion['label']}, which beat the no-change "
            f"guess with a holdout skill of {_pct(hold.get('skill'), 2)}."
        )
        text += _closest(best) if best is not None else ""
    if hold.get("coverage") is not None:
        text += (
            f" The champion's 80% range contained the actual close "
            f"{_pct(hold['coverage'], 1, False)} of the time on the holdout, across {stocks}."
        )
    lines += [
        text,
        "",
        "| Model | Selection skill | DM p | Holdout skill | 80% range coverage | Gates |",
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
    b0_mae = (models.get("B0") or {}).get("selection", {}).get("mae")
    example = (
        f" (an average miss of {_pct(b0_mae * 0.99, 3, False)} of the price instead of "
        f"{_pct(b0_mae, 3, False)})"
        if isinstance(b0_mae, int | float) and math.isfinite(b0_mae)
        else ""
    )
    lines += [
        "",
        "Skill is 1 − (the model's average miss ÷ the no-change guess's average miss), so +1% "
        f"means a miss 1% smaller than the no-change guess's{example} and a negative skill means "
        "a larger one. DM p is the one-sided Diebold–Mariano p-value for that difference. "
        "Coverage is for the selection period. [docs/methodology.md](docs/methodology.md#gates) "
        "defines the gates, and [docs/results.md](docs/results.md) has the full results.",
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
