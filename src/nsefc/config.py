"""Settings loading and validation (ENGINEERING.md 33.2).

Layers, later wins: ``config/base.yaml`` -> ``config/providers.yaml`` -> ``config/{env}.yaml``
-> environment variables ``NSEFC__SECTION__KEY`` -> explicit overrides (CLI flags).
Unknown keys or invalid values stop the process before it does anything. Secrets come only
from environment variables and are never part of the YAML layers.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import time
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from nsefc.domain import Environment, PriceBasis

ENV_PREFIX = "NSEFC__"
SECRET_ENV = {
    "r2_account_id": "NSEFC_R2_ACCOUNT_ID",
    "r2_access_key_id": "NSEFC_R2_ACCESS_KEY_ID",
    "r2_secret_access_key": "NSEFC_R2_SECRET_ACCESS_KEY",
    "healthcheck_url": "NSEFC_HEALTHCHECK_URL",
}


class ConfigError(RuntimeError):
    """The configuration could not be loaded or is invalid."""


class _Strict(BaseModel):
    # hide_input_in_errors: a failed whole-settings rule would otherwise print a truncated copy
    # of the input, whose tail is the last secret set (review finding, Phase 0).
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class StorageSettings(_Strict):
    backend: Literal["local", "r2"] = "local"
    local_root: Path = Path("var")
    private_bucket: str = "nsefc-data"
    public_bucket: str = "nsefc-public"
    scratch_bucket: str = "nsefc-scratch"
    public_base_url: str = "http://localhost:5173/api/v1"
    read_only: bool = False


class PolitenessSettings(_Strict):
    user_agent: str = "nsefc/0.1 (+https://github.com/duotkuerduot/NSE-Time-Series)"
    min_seconds_between_requests: float = Field(default=1.0, ge=1.0)
    timeout_seconds: float = Field(default=30.0, gt=0)
    retries: int = Field(default=3, ge=0, le=5)


class ProviderDefinition(_Strict):
    """One candidate source. URL template tokens are listed in config/providers.yaml."""

    provider_id: str
    name: str
    role: Literal["primary_candidate", "validator_candidate", "backfill_candidate", "excluded"]
    price_basis: PriceBasis
    url_template: str | None = None
    format: Literal["pdf", "html", "csv", "xlsx", "unknown"] = "unknown"
    fields: list[str] = Field(default_factory=list)
    terms_url: str | None = None
    notes: str = ""
    spike: bool = True

    @field_validator("provider_id")
    @classmethod
    def _slug(cls, value: str) -> str:
        if not value.replace("_", "").isalnum() or value.lower() != value:
            raise ValueError("provider_id must be a lower-case slug")
        return value


class ProvidersSettings(_Strict):
    chain: list[str] = Field(default_factory=list)
    politeness: PolitenessSettings = PolitenessSettings()
    registry: list[ProviderDefinition] = Field(default_factory=list)

    @model_validator(mode="after")
    def _chain_known(self) -> ProvidersSettings:
        known = {p.provider_id for p in self.registry}
        unknown = [p for p in self.chain if p not in known]
        if unknown:
            raise ValueError(f"provider chain names unknown providers: {unknown}")
        if len(known) != len(self.registry):
            raise ValueError("duplicate provider_id in registry")
        return self

    def get(self, provider_id: str) -> ProviderDefinition:
        for provider in self.registry:
            if provider.provider_id == provider_id:
                return provider
        raise KeyError(provider_id)


class CalendarSettings(_Strict):
    holidays_file: Path = Path("config/calendar/nse_holidays.yaml")
    coverage_warning_days: int = Field(default=60, ge=1)


class PipelineSettings(_Strict):
    freshness_deadline_eat: time = time(22, 0)
    preopen_cutoff_eat: time = time(
        8, 45
    )  # pre-trading opens 08:45 (NSE Equity Trading Rules 6.1.3)

    @field_validator("freshness_deadline_eat", "preopen_cutoff_eat", mode="before")
    @classmethod
    def _quoted_times(cls, value: object) -> object:
        # YAML 1.1 reads an unquoted 22:00 as the integer 1320 (base 60), which would silently
        # become 00:22:00. Require "HH:MM" strings or time objects.
        if isinstance(value, int | float):
            raise ValueError('write times as quoted "HH:MM" strings')
        return value


class RefitSettings(_Strict):
    schedule: Literal["daily", "weekly", "monthly"] = "monthly"


class PublishingSettings(_Strict):
    releases_retained: int = Field(default=30, ge=1)
    movers_min_turnover_kes: float = Field(default=100_000, ge=0)
    movers_count: int = Field(default=5, ge=1, le=20)


class SpikeSettings(_Strict):
    # Raw files go to the private bucket under raw/; observations under spike/observations/.
    store_files: bool = True


class Secrets(_Strict):
    r2_account_id: SecretStr | None = None
    r2_access_key_id: SecretStr | None = None
    r2_secret_access_key: SecretStr | None = None
    healthcheck_url: SecretStr | None = None

    @property
    def has_r2(self) -> bool:
        return all((self.r2_account_id, self.r2_access_key_id, self.r2_secret_access_key))


class Settings(_Strict):
    env: Environment
    storage: StorageSettings = StorageSettings()
    providers: ProvidersSettings = ProvidersSettings()
    calendar: CalendarSettings = CalendarSettings()
    pipeline: PipelineSettings = PipelineSettings()
    refit: RefitSettings = RefitSettings()
    publishing: PublishingSettings = PublishingSettings()
    spike: SpikeSettings = SpikeSettings()
    secrets: Secrets = Secrets()

    @model_validator(mode="after")
    def _environment_rules(self) -> Settings:
        if self.env is Environment.PRODUCTION and self.storage.backend != "r2":
            raise ValueError("production must use the r2 storage backend")
        if self.env is Environment.DRYRUN and not self.storage.read_only:
            raise ValueError("dryrun must read production state read-only (29.4)")
        return self


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
    if "secrets" in loaded:
        raise ConfigError(f"{path}: secrets must come from environment variables, not files")
    return loaded


def _nest(dotted: str, value: Any) -> dict[str, Any]:
    keys = [k for k in dotted.split(".") if k]
    if not keys:
        raise ConfigError(f"empty override key: {dotted!r}")
    nested: dict[str, Any] = {keys[-1]: value}
    for key in reversed(keys[:-1]):
        nested = {key: nested}
    return nested


def _env_overrides(environ: Mapping[str, str]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for name, raw in sorted(environ.items()):
        if not name.startswith(ENV_PREFIX):
            continue
        dotted = name[len(ENV_PREFIX) :].lower().replace("__", ".")
        # Values stay strings (pydantic converts them); JSON is accepted for lists and maps.
        # Parsing with YAML would turn "21:30" into the base-60 integer 1290.
        value: Any = raw
        if raw.strip().startswith(("[", "{")):
            try:
                value = json.loads(raw)
            except json.JSONDecodeError as exc:  # the value itself is not echoed
                raise ConfigError(f"{name}: not valid JSON ({exc.msg})") from None
        merged = _deep_merge(merged, _nest(dotted, value))
    return merged


def _secrets_from(environ: Mapping[str, str]) -> dict[str, str]:
    return {field: environ[var] for field, var in SECRET_ENV.items() if environ.get(var)}


def load_settings(
    env: str | Environment | None = None,
    *,
    config_dir: Path = Path("config"),
    overrides: Mapping[str, Any] | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Load, merge and validate settings. Raises ConfigError on any problem."""
    environ = os.environ if environ is None else environ
    env_name = str(env or environ.get("NSEFC_ENV") or Environment.DEVELOPMENT)
    try:
        environment = Environment(env_name)
    except ValueError as exc:
        raise ConfigError(f"unknown environment {env_name!r}") from exc

    data: dict[str, Any] = {}
    for layer in ("base.yaml", "providers.yaml", f"{environment.value}.yaml"):
        data = _deep_merge(data, _read_yaml(config_dir / layer))
    data = _deep_merge(data, _env_overrides(environ))
    for dotted, value in (overrides or {}).items():
        data = _deep_merge(data, _nest(dotted, value))
    data["env"] = environment.value
    data["secrets"] = _secrets_from(environ)
    try:
        return Settings.model_validate(data)
    except ValueError as exc:  # pydantic.ValidationError subclasses ValueError
        raise ConfigError(f"invalid configuration for {environment.value}:\n{exc}") from exc


def redacted(settings: Settings) -> dict[str, Any]:
    """The resolved configuration as plain data, with every secret replaced."""
    dumped: dict[str, Any] = settings.model_dump(mode="json")
    dumped["secrets"] = {
        key: ("***" if value else None) for key, value in dumped["secrets"].items()
    }
    return dumped


def settings_hash(settings: Settings) -> str:
    """Stable SHA-256 of the redacted configuration, recorded in pipeline_run."""
    dumped = redacted(settings)
    dumped.pop("secrets")  # presence of credentials must not change the configuration hash
    canonical = json.dumps(dumped, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
