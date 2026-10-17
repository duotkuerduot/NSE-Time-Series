"""Where everything lives under ``data/`` (§6.1). One place, so no stage guesses a path."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DataLayout:
    root: Path

    # raw downloads and imports, never modified
    @property
    def raw(self) -> Path:
        return self.root / "raw"

    @property
    def imports(self) -> Path:
        return self.raw / "imports"

    # canonical panel
    @property
    def canonical(self) -> Path:
        return self.root / "canonical"

    @property
    def bars(self) -> Path:
        return self.canonical / "bars.parquet"

    @property
    def indices(self) -> Path:
        return self.canonical / "indices.parquet"

    @property
    def securities(self) -> Path:
        return self.canonical / "securities.parquet"

    @property
    def sessions(self) -> Path:
        return self.canonical / "sessions.parquet"

    @property
    def ingest_report(self) -> Path:
        return self.canonical / "ingest_report.json"

    # derived
    @property
    def features(self) -> Path:
        return self.root / "features"

    @property
    def models(self) -> Path:
        return self.root / "models"

    @property
    def predictions(self) -> Path:
        return self.root / "predictions"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def api(self) -> Path:
        return self.root / "api" / "v1"

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def latest_run(self) -> Path:
        return self.runs / "latest.json"

    def stamp(self, stage: str) -> Path:
        """The fingerprint record a stage leaves beside its outputs (§19 step 3)."""
        return self.root / "stamps" / f"{stage}.json"
