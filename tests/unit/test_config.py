"""Layered settings: default.yaml, a profile overlay, NSEFC_DATA_DIR, then overrides."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from nsefc.config import ConfigError, find_project_root, load_settings


@pytest.mark.parametrize("profile", ["default", "sample", "test"])
def test_every_profile_loads(repo_root: Path, profile: str) -> None:
    settings = load_settings(profile, project_root=repo_root, environ={})  # type: ignore[arg-type]
    assert settings.profile_name == profile
    assert set(settings.model_specs) == {"ridge", "huber", "lightgbm", "catboost"}
    assert settings.profiles["default"].tune is False
    assert settings.profiles["full"].tune is True


def test_sample_profile_shortens_the_periods(repo_root: Path) -> None:
    default = load_settings("default", project_root=repo_root, environ={})
    sample = load_settings("sample", project_root=repo_root, environ={})
    assert default.periods.holdout_start.year == 2023
    assert sample.periods.holdout_start.year == 2021
    assert sample.universe.min_history < default.universe.min_history


def test_paths_resolve_against_the_project_root(repo_root: Path) -> None:
    settings = load_settings("default", project_root=repo_root, environ={})
    assert settings.data_dir == repo_root / "data"
    assert settings.source_dir == repo_root / "data" / "source"
    assert settings.citation_file == repo_root / "reference" / "mendeley.yaml"
    assert settings.holidays_file.is_file()
    assert settings.site_file.is_file()


def test_data_dir_environment_override(repo_root: Path, tmp_path: Path) -> None:
    settings = load_settings(
        "default", project_root=repo_root, environ={"NSEFC_DATA_DIR": str(tmp_path)}
    )
    assert settings.data_dir == tmp_path
    assert settings.source_dir == tmp_path / "source"  # the dataset moves with the data folder


def test_source_dir_can_point_elsewhere(repo_root: Path, tmp_path: Path) -> None:
    settings = load_settings(
        "default", project_root=repo_root, environ={}, overrides={"paths.source_dir": "downloads"}
    )
    assert settings.source_dir == repo_root / "downloads"
    absolute = load_settings(
        "default", project_root=repo_root, environ={}, overrides={"paths.source_dir": tmp_path}
    )
    assert absolute.source_dir == tmp_path


def test_overrides_win(repo_root: Path) -> None:
    settings = load_settings(
        "default", project_root=repo_root, environ={}, overrides={"universe.min_history": 300}
    )
    assert settings.universe.min_history == 300


def test_unknown_key_is_an_error(repo_root: Path) -> None:
    with pytest.raises(ConfigError, match="extra"):
        load_settings(
            "default", project_root=repo_root, environ={}, overrides={"universe.colour": "red"}
        )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("features.max_lookback", 20),  # must exceed the longest window
        ("periods.holdout_start", "2019-01-01"),  # inside the selection period
        ("quality.band", 2.0),
        ("gates.plaus_direction_max", 1.5),
    ],
)
def test_invalid_values_are_errors(repo_root: Path, key: str, value: object) -> None:
    with pytest.raises(ConfigError):
        load_settings("default", project_root=repo_root, environ={}, overrides={key: value})


def test_section_hash_tracks_only_its_sections(repo_root: Path) -> None:
    base = load_settings("default", project_root=repo_root, environ={})
    changed = load_settings(
        "default", project_root=repo_root, environ={}, overrides={"gates.skill_min": 0.02}
    )
    assert base.section_hash("features") == changed.section_hash("features")
    assert base.section_hash("gates") != changed.section_hash("gates")


def test_every_config_file_is_valid_yaml(repo_root: Path) -> None:
    for path in (repo_root / "config").rglob("*.yaml"):
        assert yaml.safe_load(path.read_text(encoding="utf-8")) is not None, path


def test_model_files_freeze_values_and_bound_searches(repo_root: Path) -> None:
    settings = load_settings("default", project_root=repo_root, environ={})
    lightgbm = settings.model_specs["lightgbm"]
    assert lightgbm.frozen["objective"] == "l1"
    for name, space in lightgbm.search.items():
        assert "choices" in space or space["low"] < space["high"], name


def test_project_root_is_found_from_a_subfolder(repo_root: Path) -> None:
    assert find_project_root(repo_root / "src" / "nsefc") == repo_root


def test_no_secrets_or_cloud_settings_remain(repo_root: Path) -> None:
    text = (repo_root / "config" / "default.yaml").read_text(encoding="utf-8").lower()
    for word in ("r2", "secret", "token", "bucket", "production"):
        assert f"{word}:" not in text, word
