"""Settings: one validated file of tunables (ENGINEERING.md §14).

``config/default.yaml`` holds every value. ``--sample`` loads ``config/sample.yaml`` over it and
the test suite loads ``config/test.yaml``. Explicit overrides (CLI flags) come last. Unknown keys
and invalid values stop the run before it does anything. There are no secrets and no required
environment variables; ``NSEFC_DATA_DIR`` may move the data folder.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Profile = Literal["default", "sample", "test"]
RefitFrequency = Literal["monthly", "quarterly", "semiannual", "annual"]
Candidate = Literal["ridge", "huber", "lightgbm", "catboost"]
MODEL_FILES = ("baselines", "ridge", "huber", "lightgbm", "catboost")


class ConfigError(RuntimeError):
    """The configuration could not be loaded or is invalid."""


def find_project_root(start: Path | None = None) -> Path:
    """The folder holding ``config/default.yaml``: the clone's root.

    The package is installed in editable mode by ``uv run``, so the source tree is two levels
    above this file. Falls back to searching upwards from the working directory.
    """
    here = Path(__file__).resolve().parents[2]
    origin = (start or Path.cwd()).resolve()
    candidates = [here, origin, *origin.parents]
    for folder in candidates:
        if (folder / "config" / "default.yaml").is_file():
            return folder
    raise ConfigError("cannot find config/default.yaml; run nsefc from a clone of the repository")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PathSettings(_Strict):
    data_dir: Path = Path("data")


class DatasetSettings(_Strict):
    citation_file: Path = Path("reference/mendeley.yaml")


class CalendarSettings(_Strict):
    holidays_file: Path = Path("config/calendar/nse_holidays.yaml")


class QualitySettings(_Strict):
    band: float = Field(0.10, gt=0, lt=1)
    event_margin: float = Field(0.005, ge=0, lt=0.1)
    mkt_min_share: float = Field(0.70, gt=0, le=1)
    mkt_window: int = Field(20, ge=2)
    vwap_tolerance: float = Field(0.02, gt=0)

    @property
    def event_threshold(self) -> float:
        """An absolute move above this is an event (PRC-01, §6.7)."""
        return self.band + self.event_margin


class FeatureSettings(_Strict):
    returns: list[int] = Field(default_factory=lambda: [1, 2, 3, 5, 10, 20])
    sma: list[int] = Field(default_factory=lambda: [5, 20, 50])
    high_low_window: int = Field(250, ge=20)
    volatility_windows: list[int] = Field(default_factory=lambda: [5, 20])
    ewma_lambda: float = Field(0.94, gt=0, lt=1)
    liquidity_window: int = Field(20, ge=5)
    market_returns: list[int] = Field(default_factory=lambda: [1, 5])
    max_lookback: int = Field(60, ge=5)

    @model_validator(mode="after")
    def _lookback_covers_windows(self) -> FeatureSettings:
        longest = max([*self.returns, *self.sma, *self.volatility_windows, self.liquidity_window])
        if longest >= self.max_lookback:
            raise ValueError(f"max_lookback {self.max_lookback} must exceed the longest window")
        return self


class TargetSettings(_Strict):
    winsorise: float = Field(0.105, gt=0, lt=1)


class UniverseSettings(_Strict):
    window: int = Field(250, ge=20)
    min_traded_share: float = Field(0.80, ge=0, le=1)
    min_median_turnover_kes: float = Field(1_000_000, ge=0)
    min_history: int = Field(500, ge=1)


class PeriodSettings(_Strict):
    tuning: tuple[date, date]
    selection: tuple[date, date]
    holdout_start: date
    calibration_warmup_sessions: int = Field(250, ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> PeriodSettings:
        if not (
            self.tuning[0]
            <= self.tuning[1]
            < self.selection[0]
            <= self.selection[1]
            < self.holdout_start
        ):
            raise ValueError("periods must run tuning < selection < holdout, in order")
        return self


class EvaluationSettings(_Strict):
    dm_lags: int = Field(5, ge=0)
    flat_threshold: float = Field(0.001, ge=0)


class IntervalSettings(_Strict):
    level: float = Field(0.80, gt=0, lt=1)
    ewma_lambda: float = Field(0.94, gt=0, lt=1)
    sigma_floor: float = Field(0.0025, gt=0)
    calibration_window: int = Field(250, ge=20)


class GateSettings(_Strict):
    """§11.4, fixed before results are seen (changing one afterwards needs the owner, §0.6)."""

    skill_min: float = Field(0.01, gt=-1, lt=1)
    skill_p_max: float = Field(0.05, gt=0, lt=1)
    base_p_max: float = Field(0.10, gt=0, lt=1)
    stab_min_positive_share: float = Field(0.80, ge=0, le=1)
    stab_year_floor: float = Field(-0.02, gt=-1, lt=1)
    dir_alpha: float = Field(0.05, gt=0, lt=1)
    cal_low: float = Field(0.75, ge=0, le=1)
    cal_high: float = Field(0.85, ge=0, le=1)
    hold_min_ratio: float = Field(0.50, ge=0)
    plaus_skill_max: float = Field(0.15, gt=0, lt=1)
    plaus_direction_max: float = Field(0.65, gt=0.5, le=1)

    @model_validator(mode="after")
    def _ordered(self) -> GateSettings:
        if self.cal_low > self.cal_high:
            raise ValueError("gates.cal_low must not exceed gates.cal_high")
        return self


class ProfileSettings(_Strict):
    refit: RefitFrequency
    candidates: list[Candidate]
    tune: bool = False
    trials: int = Field(40, ge=1)


class ModelSettings(_Strict):
    b1_window: int = Field(250, ge=5)
    b2_window: int = Field(5, ge=2)
    b3_window: int = Field(500, ge=20)
    early_stopping_share: float = Field(0.10, gt=0, lt=0.5)


class PublishingSettings(_Strict):
    movers_count: int = Field(5, ge=1)
    movers_min_turnover_kes: float = Field(100_000, ge=0)
    history_rows: int = Field(250, ge=1)
    index_trend_sessions: int = Field(250, ge=2)
    breadth_sessions: int = Field(60, ge=2)
    track_record_window: int = Field(60, ge=5)


class ServeSettings(_Strict):
    host: str = "127.0.0.1"
    port: int = Field(8000, ge=1, le=65535)
    port_tries: int = Field(10, ge=1)


class RuntimeSettings(_Strict):
    threads: int = Field(4, ge=1)
    seed: int = 20261016


class ModelSpec(_Strict):
    """One file in config/models: a display label, frozen values, and a search space."""

    label: str
    frozen: dict[str, Any] = Field(default_factory=dict)
    search: dict[str, Any] = Field(default_factory=dict)


class Settings(_Strict):
    profile_name: Profile = "default"
    project_root: Path
    paths: PathSettings = PathSettings()
    dataset: DatasetSettings = DatasetSettings()
    calendar: CalendarSettings = CalendarSettings()
    quality: QualitySettings = QualitySettings()
    features: FeatureSettings = FeatureSettings()
    targets: TargetSettings = TargetSettings()
    universe: UniverseSettings = UniverseSettings()
    periods: PeriodSettings
    evaluation: EvaluationSettings = EvaluationSettings()
    intervals: IntervalSettings = IntervalSettings()
    gates: GateSettings = GateSettings()
    profiles: dict[Literal["default", "full"], ProfileSettings]
    models: ModelSettings = ModelSettings()
    publishing: PublishingSettings = PublishingSettings()
    serve: ServeSettings = ServeSettings()
    runtime: RuntimeSettings = RuntimeSettings()
    model_specs: dict[str, ModelSpec] = Field(default_factory=dict)
    baselines: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @property
    def data_dir(self) -> Path:
        path = self.paths.data_dir
        return path if path.is_absolute() else self.project_root / path

    @property
    def holidays_file(self) -> Path:
        path = self.calendar.holidays_file
        return path if path.is_absolute() else self.project_root / path

    @property
    def reference_dir(self) -> Path:
        return self.project_root / "reference"

    @property
    def site_file(self) -> Path:
        return self.project_root / "config" / "site.yaml"

    @property
    def citation_file(self) -> Path:
        path = self.dataset.citation_file
        return path if path.is_absolute() else self.project_root / path

    def section_hash(self, *names: str) -> str:
        """SHA-256 of the named sections, for stage fingerprints (§19)."""
        dumped = self.model_dump(mode="json", include=set(names))
        canonical = json.dumps(dumped, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"missing configuration file: {path}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ConfigError(f"{path} must contain a mapping at the top level")
    return loaded


def _nest(dotted: str, value: Any) -> dict[str, Any]:
    keys = [k for k in dotted.split(".") if k]
    if not keys:
        raise ConfigError(f"empty override key: {dotted!r}")
    nested: dict[str, Any] = {keys[-1]: value}
    for key in reversed(keys[:-1]):
        nested = {key: nested}
    return nested


def load_settings(
    profile: Profile = "default",
    *,
    project_root: Path | None = None,
    overrides: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Load default.yaml, the profile overlay and overrides; validate. Raises ConfigError."""
    root = project_root or find_project_root()
    environ = os.environ if environ is None else environ
    config_dir = root / "config"
    data = _read_yaml(config_dir / "default.yaml")
    if profile != "default":
        data = _deep_merge(data, _read_yaml(config_dir / f"{profile}.yaml"))
    if environ.get("NSEFC_DATA_DIR"):
        data = _deep_merge(data, {"paths": {"data_dir": environ["NSEFC_DATA_DIR"]}})
    for dotted, value in (overrides or {}).items():
        data = _deep_merge(data, _nest(dotted, value))
    data["profile_name"] = profile
    data["project_root"] = root
    models_dir = config_dir / "models"
    data["baselines"] = _read_yaml(models_dir / "baselines.yaml")
    data["model_specs"] = {
        name: _read_yaml(models_dir / f"{name}.yaml") for name in MODEL_FILES if name != "baselines"
    }
    try:
        return Settings.model_validate(data)
    except ValueError as exc:  # pydantic.ValidationError subclasses ValueError
        raise ConfigError(f"invalid configuration ({profile}):\n{exc}") from exc
