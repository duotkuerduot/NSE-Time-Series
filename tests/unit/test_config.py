from __future__ import annotations

import shutil
from datetime import time
from pathlib import Path

import pytest
import yaml

from nsefc.config import ConfigError, load_settings, redacted, settings_hash
from nsefc.domain import Environment


@pytest.fixture
def config_dir(repo_root: Path) -> Path:
    return repo_root / "config"


@pytest.mark.parametrize("env", list(Environment))
def test_every_environment_loads(config_dir: Path, env: Environment) -> None:
    settings = load_settings(env, config_dir=config_dir, environ={})
    assert settings.env is env


def test_production_rules(config_dir: Path) -> None:
    production = load_settings("production", config_dir=config_dir, environ={})
    assert production.storage.backend == "r2"
    assert production.providers.chain == ["nse_pricelist", "kingdom"]
    dryrun = load_settings("dryrun", config_dir=config_dir, environ={})
    assert dryrun.storage.read_only


def test_environment_variable_override(config_dir: Path) -> None:
    settings = load_settings(
        "development",
        config_dir=config_dir,
        environ={
            "NSEFC__PIPELINE__FRESHNESS_DEADLINE_EAT": "21:30",
            "NSEFC__PUBLISHING__MOVERS_COUNT": "7",
        },
    )
    assert settings.pipeline.freshness_deadline_eat == time(21, 30)
    assert settings.publishing.movers_count == 7


def test_cli_override_wins(config_dir: Path) -> None:
    settings = load_settings(
        "development",
        config_dir=config_dir,
        environ={"NSEFC__REFIT__SCHEDULE": "weekly"},
        overrides={"refit.schedule": "daily"},
    )
    assert settings.refit.schedule == "daily"


def test_unknown_key_is_rejected(config_dir: Path) -> None:
    with pytest.raises(ConfigError, match="extra"):
        load_settings(
            "development",
            config_dir=config_dir,
            environ={"NSEFC__PIPELINE__FRESHNES_DEADLINE": "22:00"},
        )


def test_invalid_value_is_rejected(config_dir: Path) -> None:
    with pytest.raises(ConfigError):
        load_settings(
            "development",
            config_dir=config_dir,
            environ={"NSEFC__PROVIDERS__POLITENESS__MIN_SECONDS_BETWEEN_REQUESTS": "0.1"},
        )


def test_unknown_environment(config_dir: Path) -> None:
    with pytest.raises(ConfigError, match="unknown environment"):
        load_settings("staging", config_dir=config_dir, environ={})


def test_secrets_never_from_files(tmp_path: Path, config_dir: Path) -> None:
    for name in ("base.yaml", "providers.yaml", "development.yaml"):
        shutil.copy(config_dir / name, tmp_path / name)
    with (tmp_path / "development.yaml").open("a") as handle:
        handle.write("\nsecrets:\n  r2_access_key_id: leaked\n")
    with pytest.raises(ConfigError, match="secrets"):
        load_settings("development", config_dir=tmp_path, environ={})


def test_secrets_redacted_and_excluded_from_hash(config_dir: Path) -> None:
    plain = load_settings("development", config_dir=config_dir, environ={})
    with_secret = load_settings(
        "development", config_dir=config_dir, environ={"NSEFC_R2_ACCESS_KEY_ID": "AKIA-very-secret"}
    )
    dumped = redacted(with_secret)
    assert dumped["secrets"]["r2_access_key_id"] == "***"
    assert "AKIA-very-secret" not in str(dumped)
    assert settings_hash(plain) == settings_hash(with_secret)


def test_chain_must_name_known_providers(tmp_path: Path, config_dir: Path) -> None:
    for name in ("base.yaml", "providers.yaml", "development.yaml"):
        shutil.copy(config_dir / name, tmp_path / name)
    (tmp_path / "development.yaml").write_text(yaml.safe_dump({"providers": {"chain": ["nope"]}}))
    with pytest.raises(ConfigError, match="unknown providers"):
        load_settings("development", config_dir=tmp_path, environ={})


def test_every_config_file_is_valid_yaml(config_dir: Path) -> None:
    for path in config_dir.rglob("*.yaml"):
        assert isinstance(yaml.safe_load(path.read_text()), dict), path


def test_champion_pointer_shape(config_dir: Path) -> None:
    champion = yaml.safe_load((config_dir / "champion.yaml").read_text())
    assert set(champion) == {"champion", "artifact_sha256", "previous_champion"}


def test_list_override_as_json(config_dir: Path) -> None:
    settings = load_settings(
        "development", config_dir=config_dir, environ={"NSEFC__PROVIDERS__CHAIN": '["kingdom"]'}
    )
    assert settings.providers.chain == ["kingdom"]


def test_unquoted_yaml_time_is_rejected(tmp_path: Path, config_dir: Path) -> None:
    for name in ("base.yaml", "providers.yaml"):
        shutil.copy(config_dir / name, tmp_path / name)
    (tmp_path / "development.yaml").write_text("pipeline:\n  freshness_deadline_eat: 22:00\n")
    with pytest.raises(ConfigError, match="quoted"):
        load_settings("development", config_dir=tmp_path, environ={})


def test_validation_errors_never_echo_secrets(config_dir: Path) -> None:
    environ = {
        "NSEFC_R2_ACCESS_KEY_ID": "AKIDEXAMPLEKEYID",
        "NSEFC_R2_SECRET_ACCESS_KEY": "wJalrXUtnFEMI-K7MDENG-bPxRfiCYEXAMPLEKEY",
        "NSEFC_HEALTHCHECK_URL": "https://hc-ping.com/0f6a-secret-uuid",
        "NSEFC__STORAGE__BACKEND": "local",  # production requires r2: a whole-settings error
    }
    with pytest.raises(ConfigError) as caught:
        load_settings("production", config_dir=config_dir, environ=environ)
    message = f"{caught.value}\n{caught.value.__cause__}"
    assert "requires" in message or "r2" in message
    for fragment in ("EXAMPLEKEY", "secret-uuid", "AKIDEXAMPLE"):
        assert fragment not in message


def test_malformed_json_override_is_a_config_error(config_dir: Path) -> None:
    with pytest.raises(ConfigError, match="NSEFC__PROVIDERS__CHAIN: not valid JSON"):
        load_settings(
            "development",
            config_dir=config_dir,
            environ={"NSEFC__PROVIDERS__CHAIN": '["kingdom",'},
        )
