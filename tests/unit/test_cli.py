from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from nsefc import cli
from nsefc.ingestion import spike
from nsefc.ingestion.spike import Observation, load_observations
from nsefc.storage.objectstore import LocalObjectStore

runner = CliRunner()


@pytest.fixture
def in_repo(repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run commands from the repository root, with local storage in a temporary directory."""
    monkeypatch.chdir(repo_root)
    monkeypatch.setenv("NSEFC__STORAGE__LOCAL_ROOT", str(tmp_path))
    return tmp_path


def test_probe_keeps_observations_made_before_a_crash(
    in_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_observe(client, provider, session_date, *, mode, store, now=None):  # type: ignore[no-untyped-def]
        if provider.provider_id == "kingdom":
            raise RuntimeError("runner lost its network")
        return Observation(
            provider.provider_id,
            session_date,
            "https://example.test/file.pdf",
            datetime(2026, 10, 7, 15, 10, tzinfo=UTC),
            mode,
            404,
            False,
        )

    monkeypatch.setattr(spike, "observe", fake_observe)
    result = runner.invoke(
        cli.app, ["spike", "probe", "--env", "ci", "--as-of", "2026-10-07", "--no-store"]
    )
    assert isinstance(result.exception, RuntimeError)
    saved = load_observations(LocalObjectStore(in_repo / "private"))
    assert [(o.provider_id, o.session_date) for o in saved] == [
        ("nse_pricelist", date(2026, 10, 7))
    ]


def test_backcheck_rejects_a_blank_date(in_repo: Path) -> None:
    result = runner.invoke(
        cli.app, ["spike", "backcheck", "--env", "ci", "--from", "", "--to", "2026-10-07"]
    )
    assert result.exit_code == 2
    assert "--from must be a date" in result.output


@pytest.mark.parametrize("command", [["data", "profile"], ["calendar", "reconcile"]])
def test_data_commands_fail_without_price_files(
    in_repo: Path, tmp_path: Path, command: list[str]
) -> None:
    result = runner.invoke(cli.app, [*command, "--data-dir", str(tmp_path / "missing")])
    assert result.exit_code == 2
    assert "no NSE_data_all_stocks_*.csv files" in result.output
