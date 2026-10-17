"""Documented corrections to the source data (§6.4).

Each rule in ``reference/corrections.yaml`` is keyed to the SHA-256 of the one file it fixes,
so it can never silently apply to a different dataset version: if the file changes, the rule
stops matching and the check it was suppressing (for example DAT-01) reports the problem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal

import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class CorrectionError(ValueError):
    """A correction rule is malformed or would create a conflict (blocks the run)."""


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    file: str = Field(description="File name, for readers; matching uses sha256")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: Literal["redate", "drop"]
    lines: tuple[int, int] = Field(description="Inclusive file line numbers; the header is line 1")
    from_date: date | None = Field(None, alias="from")
    to_date: date | None = Field(None, alias="to")
    reason: str

    @model_validator(mode="after")
    def _shape(self) -> Rule:
        if self.lines[0] < 2 or self.lines[1] < self.lines[0]:
            raise ValueError(f"{self.id}: lines must be [first, last] with first >= 2")
        if self.action == "redate" and (self.from_date is None or self.to_date is None):
            raise ValueError(f"{self.id}: redate needs from and to")
        return self


class CorrectionsFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    corrections: list[Rule] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> CorrectionsFile:
        ids = [r.id for r in self.corrections]
        if len(ids) != len(set(ids)):
            raise ValueError("correction ids must be unique")
        return self


@dataclass(slots=True)
class Applied:
    rule: Rule
    rows: int


@dataclass(slots=True)
class CorrectionReport:
    applied: list[Applied] = field(default_factory=list)
    not_applicable: list[Rule] = field(default_factory=list)  # keyed to files not in this run


def load_corrections(path: Path) -> CorrectionsFile:
    if not path.is_file():
        return CorrectionsFile(version=1)
    try:
        return CorrectionsFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except ValueError as exc:
        raise CorrectionError(f"invalid {path.name}: {exc}") from exc


def apply_corrections(
    raw: pd.DataFrame, rules: CorrectionsFile
) -> tuple[pd.DataFrame, CorrectionReport]:
    """Apply every rule whose file is present. Returns the corrected frame and a report."""
    report = CorrectionReport()
    frame = raw.copy()
    present = set(frame["source_file_sha256"].unique())
    drop_mask = pd.Series(False, index=frame.index)
    for rule in rules.corrections:
        if rule.sha256 not in present:
            report.not_applicable.append(rule)
            continue
        selected = (frame["source_file_sha256"] == rule.sha256) & frame["line"].between(
            rule.lines[0], rule.lines[1]
        )
        if rule.action == "redate":
            assert rule.from_date is not None
            assert rule.to_date is not None
            selected &= frame["session_date"] == pd.Timestamp(rule.from_date)
            target = pd.Timestamp(rule.to_date)
            clash = (
                (frame["source_file_sha256"] == rule.sha256)
                & (frame["session_date"] == target)
                & ~selected
            )
            moving_codes = set(frame.loc[selected, "code"])
            if clash.any() and moving_codes & set(frame.loc[clash, "code"]):
                raise CorrectionError(
                    f"{rule.id}: {rule.to_date} already has rows for the same securities "
                    f"in {rule.file}"
                )
            frame.loc[selected, "session_date"] = target
        else:
            drop_mask |= selected
        count = int(selected.sum())
        if count == 0:
            raise CorrectionError(
                f"{rule.id}: matches no rows in {rule.file}; fix or remove the rule"
            )
        report.applied.append(Applied(rule, count))
    frame = frame[~drop_mask]
    return frame, report
