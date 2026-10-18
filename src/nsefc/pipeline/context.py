"""Run context, stage fingerprints and the JSON-lines run log."""

from __future__ import annotations

import json
import platform
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from nsefc import __version__
from nsefc.calendar import TradingCalendar, load_calendar
from nsefc.config import Settings
from nsefc.storage import DataLayout, atomic_write_json, read_json, sha256_file, sha256_text

Echo = Callable[[str], None]


class StageError(RuntimeError):
    """A stage failed; ``exit_code`` is the documented exit code (docs/architecture.md)."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def utc_now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def new_run_id() -> str:
    return utc_now().strftime("%Y%m%dT%H%M%SZ")


def git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def file_hash(path: Path) -> str:
    return sha256_file(path) if path.is_file() else "absent"


PACKAGE = Path(__file__).resolve().parents[1]
# The code each stage's results depend on: a change re-runs that stage and everything
# after it, so an updated clone never reuses results computed by older code.
STAGE_CODE: dict[str, tuple[str, ...]] = {
    "ingest": (
        "acquire",
        "ingest",
        "quality",
        "calendar",
        "domain",
        "sample",
        "storage",
        "config.py",
    ),
    "features": ("features", "targets", "intervals", "evaluation/dataset.py"),
    "train": ("models", "intervals", "evaluation", "selection", "pipeline/train.py"),
    "predict": ("prediction",),
    "publish": ("publishing", "api", "pipeline/reports.py"),
}


def code_hash(stage: str) -> str:
    """SHA-256 over the stage's source files, independent of line endings."""
    files: list[Path] = []
    for entry in STAGE_CODE[stage]:
        path = PACKAGE / entry
        files += sorted(path.rglob("*.py")) if path.is_dir() else [path]
    parts = []
    for path in sorted(set(files), key=lambda p: p.relative_to(PACKAGE).as_posix()):
        parts.append(path.relative_to(PACKAGE).as_posix())
        parts.append(path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8"))
    return sha256_text(*parts)


@dataclass(slots=True)
class RunContext:
    settings: Settings
    profile: str = "default"  # "default" or "full"
    mode: str = "mendeley"  # mendeley, local or sample
    force: bool = False
    verbose: bool = False
    run_id: str = field(default_factory=new_run_id)
    echo: Echo = print
    started: float = field(default_factory=time.monotonic)
    _calendar: TradingCalendar | None = None

    @property
    def layout(self) -> DataLayout:
        return DataLayout(self.settings.data_dir)

    @property
    def calendar(self) -> TradingCalendar:
        if self._calendar is None:
            self._calendar = load_calendar(self.settings.holidays_file)
        return self._calendar

    @property
    def run_dir(self) -> Path:
        return self.layout.runs / self.run_id

    def log(self, event: str, **fields: Any) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        record = {"ts": utc_now().isoformat(), "event": event, **fields}
        with (self.run_dir / "log.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")

    def fingerprint(self, *parts: str) -> str:
        return sha256_text(__version__, *parts)


@dataclass(slots=True)
class Stamp:
    """What a stage produced, and from which inputs (``data/stamps/<stage>.json``)."""

    stage: str
    fingerprint: str
    run_id: str
    finished_at: str
    outputs: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "fingerprint": self.fingerprint,
            "run_id": self.run_id,
            "finished_at": self.finished_at,
            "outputs": self.outputs,
        }


def read_stamp(layout: DataLayout, stage: str) -> Stamp | None:
    path = layout.stamp(stage)
    if not path.is_file():
        return None
    data = read_json(path)
    return Stamp(
        data["stage"], data["fingerprint"], data["run_id"], data["finished_at"], data["outputs"]
    )


def write_stamp(layout: DataLayout, stamp: Stamp) -> None:
    atomic_write_json(layout.stamp(stamp.stage), stamp.as_dict())


def environment_summary() -> dict[str, str]:
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "nsefc": __version__,
    }
