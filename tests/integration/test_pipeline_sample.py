"""`nsefc run --sample --no-serve` end to end: published files, models, champion, caching."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from nsefc.api.export import validate_tree
from nsefc.pipeline.context import RunContext, StageError
from nsefc.pipeline.stages import stage_publish, stage_train
from nsefc.storage import read_json
from tests.conftest import CliRun, cli, settings_for


def api(run: CliRun) -> Path:
    return run.data_dir / "api" / "v1"


def snapshot(folder: Path) -> dict[str, bytes]:
    return {
        p.relative_to(folder).as_posix(): p.read_bytes()
        for p in sorted(folder.rglob("*"))
        if p.is_file()
    }


def test_the_run_succeeds(sample_run: CliRun) -> None:
    assert sample_run.exit_code == 0, sample_run.output
    for stage in ("acquire", "ingest", "train", "predict", "publish"):
        assert stage in sample_run.output
    assert "Champion:" in sample_run.output


def test_every_published_file_validates(sample_run: CliRun) -> None:
    assert validate_tree(api(sample_run)) == []


def test_status_says_sample_and_is_never_stale(sample_run: CliRun) -> None:
    status = read_json(api(sample_run) / "status.json")
    assert status["data_mode"] == "sample" and status["stale_after"] is None
    assert status["contract_version"] == "1.1" and status["dataset"]["source"] == "sample"
    assert "SAMPLE_DATA" in {n["code"] for n in status["notices"]}


def test_every_universe_security_has_a_forecast_or_a_reason(sample_run: CliRun) -> None:
    """Every forecast-universe stock has a forecast with an 80% range, or a valid reason."""
    status = read_json(api(sample_run) / "status.json")
    release = api(sample_run) / "r" / status["release_id"]
    stocks = read_json(release / "stocks.json")["items"]
    forecasts = 0
    for item in stocks:
        prediction = read_json(release / "stocks" / item["ticker"] / "prediction.json")
        assert (prediction["latest"] is None) != (prediction["unavailable_reason"] is None)
        if prediction["latest"]:
            forecasts += 1
            latest = prediction["latest"]
            assert latest["range"]["lower"] <= latest["predicted_close"] <= latest["range"]["upper"]
            assert latest["target_in_past"] is True and latest["target_session"] == "2025-01-02"
        assert item["has_forecast"] == (prediction["latest"] is not None)
    assert forecasts >= 15
    rights = read_json(release / "stocks" / "SMPL05-R" / "prediction.json")
    assert rights["unavailable_reason"] == "NOT_IN_FORECAST_UNIVERSE"


def test_every_model_went_through_the_gates(sample_run: CliRun) -> None:
    """Baselines and at least two ML candidates, and a champion chosen by the gates."""
    evaluation = read_json(sample_run.data_dir / "reports" / "evaluation.json")
    ids = {m["model_id"] for m in evaluation["models"]}
    assert {"B0", "B1", "B2", "B3", "ridge", "huber", "lightgbm"} <= ids
    for model in evaluation["models"]:
        if model["model_id"] != "B0":
            assert {g["id"] for g in model["gates"]} == {
                "G-INT",
                "G-SKILL",
                "G-BASE",
                "G-STAB",
                "G-DIR",
                "G-CAL",
                "G-HOLD",
            }
        assert model["selection"]["rows"] > 0 and model["holdout"]["rows"] > 0
    assert evaluation["champion"]["model_id"] in ids
    report = (sample_run.data_dir / "reports" / "evaluation.md").read_text(encoding="utf-8")
    assert "## Plausibility tripwire (G-PLAUS)" in report and "Not triggered" in report
    assert "excluded by the gap guard" in report
    audit = (sample_run.data_dir / "reports" / "data-audit.md").read_text(encoding="utf-8")
    assert "SAMPLE-01" in audit and "GAP-01" in audit


def test_run_records_and_logs(sample_run: CliRun) -> None:
    latest = read_json(sample_run.data_dir / "runs" / "latest.json")
    run = read_json(sample_run.data_dir / "runs" / latest["run_id"] / "run.json")
    assert run["outcome"] == "succeeded" and run["stages"]["train"]["cached"] is False
    log = (sample_run.data_dir / "runs" / latest["run_id"] / "log.jsonl").read_text(
        encoding="utf-8"
    )
    assert '"event": "train"' in log and '"event": "publish"' in log


def test_a_repeat_run_is_cached_and_byte_identical(sample_run: CliRun) -> None:
    """Idempotency and caching."""
    before = snapshot(api(sample_run))
    release = read_json(api(sample_run) / "status.json")["release_id"]
    again = cli(["run", "--sample", "--no-serve"], sample_run.data_dir)
    assert again.exit_code == 0, again.output
    for stage in ("acquire", "ingest", "train", "predict", "publish"):
        line = next(line for line in again.output.splitlines() if line.strip().startswith(stage))
        assert "cached" in line, line
    assert snapshot(api(sample_run)) == before
    assert read_json(api(sample_run) / "status.json")["release_id"] == release


def test_status_command(sample_run: CliRun) -> None:
    out = cli(["status"], sample_run.data_dir).output
    assert "Data mode:  sample" in out and "Champion:" in out and "Published:" in out


def test_sample_results_never_reach_the_readme(sample_run: CliRun) -> None:
    result = cli(["dev", "update-readme"], sample_run.data_dir)
    assert result.exit_code == 2 and "sample" in result.output


def test_imports_are_refused_in_sample_mode(sample_run: CliRun, tmp_path: Path) -> None:
    csv = tmp_path / "new.csv"
    csv.write_text("date,ticker,close,volume\n2025-01-02,SMPL01,10,100\n", encoding="utf-8")
    result = cli(["import", str(csv)], sample_run.data_dir)
    assert result.exit_code == 2 and "without --sample" in result.output


@pytest.fixture
def copied(sample_run: CliRun, tmp_path: Path) -> Path:
    target = tmp_path / "data"
    shutil.copytree(sample_run.data_dir, target)
    return target


def test_clean_keeps_raw_files_unless_all(copied: Path) -> None:
    assert cli(["clean"], copied).exit_code == 0
    assert (
        (copied / "raw").is_dir()
        and not (copied / "canonical").exists()
        and not (copied / "api").exists()
    )
    assert cli(["clean", "--all"], copied).exit_code == 0
    assert not (copied / "raw").exists()


def test_g_plaus_stops_the_run_with_exit_code_30(copied: Path) -> None:
    settings = settings_for(
        copied,
        **{
            "gates.plaus_direction_max": 0.51,
            "profiles.default.candidates": ["ridge"],
            "profiles.default.refit": "annual",
        },
    )
    ctx = RunContext(settings=settings, mode="sample", echo=lambda _m: None)
    with pytest.raises(StageError) as raised:
        stage_train(ctx)
    assert raised.value.exit_code == 30 and "G-PLAUS" in str(raised.value)


def test_a_file_that_fails_the_contract_stops_publishing_with_40(
    copied: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nsefc.publishing.build as build

    monkeypatch.setattr(
        build,
        "_load_site",
        lambda _path, attribution: {
            "owner_name": "x",
            "tagline": "",
            "links": [{"label": "bad", "url": "javascript:alert(1)"}],
            "attribution": attribution,
        },
    )
    ctx = RunContext(
        settings=settings_for(copied, profile="sample"),
        mode="sample",
        force=True,
        echo=lambda _m: None,
    )
    before = json.loads((copied / "api" / "v1" / "status.json").read_text(encoding="utf-8"))
    with pytest.raises(StageError) as raised:
        stage_publish(ctx)
    assert raised.value.exit_code == 40 and "site.json" in str(raised.value)
    # The previous release is untouched.
    assert json.loads((copied / "api" / "v1" / "status.json").read_text(encoding="utf-8")) == before


def test_stage_commands_refuse_outputs_older_than_the_data(copied: Path) -> None:
    """Changed settings (or data) make the trained models stale: predict and publish stop."""
    from nsefc.pipeline.stages import stage_predict

    settings = settings_for(copied, profile="sample", **{"gates.skill_min": 0.02})
    ctx = RunContext(settings=settings, mode="sample", echo=lambda _m: None)
    for stage in (stage_predict, stage_publish):
        with pytest.raises(StageError) as raised:
            stage(ctx)
        assert raised.value.exit_code == 2 and "run `nsefc" in str(raised.value)
