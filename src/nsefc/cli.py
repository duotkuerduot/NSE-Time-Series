"""The ``nsefc`` command line.

``uv run nsefc run`` does everything: acquire, ingest, train and evaluate, predict, publish,
then serve the app in the browser. Each stage is also a subcommand.
"""

from __future__ import annotations

import math
import sys
import time
import traceback
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console

from nsefc import __version__
from nsefc.config import ConfigError, Settings, load_settings
from nsefc.pipeline.context import RunContext, StageError, read_stamp
from nsefc.pipeline.stages import (
    StageOutcome,
    current_dataset,
    stage_acquire,
    stage_ingest,
    stage_predict,
    stage_publish,
    stage_train,
)
from nsefc.storage import (
    DataLayout,
    atomic_write_json,
    read_json,
    remove_tree,
    sha256_file,
    sweep_temporaries,
)

console = Console(highlight=False, soft_wrap=True)
err = Console(stderr=True, highlight=False, soft_wrap=True)

app = typer.Typer(
    help="NSE Forecast: next-session forecasts for the Nairobi Securities Exchange, run locally.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
)
dev_app = typer.Typer(help="Maintainer tools.", no_args_is_help=True)
app.add_typer(dev_app, name="dev")

Profile = Annotated[
    str, typer.Option("--profile", help="default, or full (tuning, monthly refits, CatBoost)")
]
Sample = Annotated[bool, typer.Option("--sample", help="Use the synthetic sample dataset")]
SourceDir = Annotated[
    Path | None,
    typer.Option("--source-dir", help="Read the dataset files from this folder, not data/source"),
]
Force = Annotated[bool, typer.Option("--force", help="Recompute every stage even if cached")]
NoBrowser = Annotated[bool, typer.Option("--no-browser", help="Do not open a browser")]
Port = Annotated[int | None, typer.Option("--port", help="Port to serve on (default from config)")]
Verbose = Annotated[bool, typer.Option("--verbose", "-v", help="Show every walk-forward refit")]


# ---------------------------------------------------------------- helpers
def _settings(sample: bool = False) -> Settings:
    try:
        return load_settings("sample" if sample else "default")
    except ConfigError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc


def _active_mode(settings: Settings) -> str | None:
    active = DataLayout(settings.data_dir).raw / "active.json"
    return str(read_json(active)["mode"]) if active.is_file() else None


def _context(
    *,
    sample: bool | None = None,
    profile: str = "default",
    force: bool = False,
    verbose: bool = False,
) -> RunContext:
    if profile not in ("default", "full"):
        err.print(f"[red]--profile must be default or full, not {profile!r}[/red]")
        raise typer.Exit(2)
    if sample is None:
        # Individual stage commands follow whatever `acquire` chose last.
        probe = _settings(False)
        sample = _active_mode(probe) == "sample"
    settings = _settings(sample)
    return RunContext(
        settings=settings,
        profile=profile,
        mode="sample" if sample else "dataset",
        force=force,
        verbose=verbose,
        echo=lambda m: console.print(f"    [dim]{m}[/dim]"),
    )


# The exit code for an unexpected failure inside each stage.
STAGE_EXIT = {"acquire": 10, "ingest": 20, "train": 30, "predict": 30, "publish": 40}


def _fail(exc: StageError) -> typer.Exit:
    err.print(f"[red]error:[/red] {exc}")
    return typer.Exit(exc.exit_code)


def _stage(ctx: RunContext, name: str, call: Callable[[], StageOutcome]) -> StageOutcome:
    """Run one stage; an unexpected exception becomes a StageError with the stage's exit code."""
    try:
        return call()
    except StageError:
        raise
    except Exception as exc:
        ctx.log("error", stage=name, error=repr(exc), traceback=traceback.format_exc())
        raise StageError(
            f"the {name} stage failed unexpectedly: {exc}\n  details: {ctx.run_dir / 'log.jsonl'}",
            STAGE_EXIT[name],
        ) from exc


def _seconds(value: float) -> str:
    if value < 60:
        return f"{value:.1f} s"
    minutes, seconds = divmod(round(value), 60)
    return f"{minutes} m {seconds} s"


def _line(outcome: StageOutcome) -> None:
    main, _, extra = outcome.summary.partition(" (")
    state = "cached" if outcome.cached else main
    detail = f"   ({extra}" if extra and not outcome.cached else ""
    if outcome.cached:
        detail = f"   [dim]{outcome.summary}[/dim]"
    console.print(f"  {outcome.stage:<9} {state:<36} {_seconds(outcome.seconds):>8}{detail}")


def _pct(value: Any, digits: int = 2, signed: bool = False) -> str:
    if not isinstance(value, int | float) or not math.isfinite(value):
        return "n/a"
    return f"{value:+.{digits}%}" if signed else f"{value:.{digits}%}"


def _header(ctx: RunContext) -> None:
    layout = ctx.layout
    if not layout.ingest_report.is_file():
        return
    report = read_json(layout.ingest_report)
    dataset = current_dataset(ctx, report)
    label = (
        "synthetic sample data"
        if report["data_mode"] == "sample"
        else dataset.get("title", "dataset")
    )
    console.print(
        f"[bold]NSE Forecast[/bold]  ·  {label}  ·  "
        f"{report['first_session']} to {report['last_session']}"
    )
    if dataset.get("citation") and report["data_mode"] != "sample":
        console.print(f"  [dim]Data: {dataset['citation']}[/dim]")
        if dataset.get("licence"):
            console.print(f"  [dim]Licence: {dataset['licence']}[/dim]")
        else:
            console.print(
                "  [dim]Licence not recorded in reference/mendeley.yaml: "
                "use the data for personal research.[/dim]"
            )


def _champion_summary(evaluation: dict[str, Any]) -> None:
    champion = evaluation["champion"]
    models = {m["model_id"]: m for m in evaluation["models"]}
    start, end = evaluation["periods"]["holdout"]
    console.print()
    console.print(
        f"[bold]Champion: {champion['label']}[/bold]  ·  holdout {start[:7]} to {end[:7]}"
    )
    hold = models[champion["model_id"]].get("holdout") or {}
    if champion["model_id"] != "B0" and hold:
        console.print(
            f"  average miss {_pct(hold['mae'])} of price vs {_pct(hold['mae_b0'])} "
            "for a no-change guess  "
            f"(skill {_pct(hold['skill'], 1, True)}, p = {hold['dm_p']:.3f})"
        )
        console.print(
            f"  80% range contained the actual close {_pct(hold['coverage'], 1)} of the time"
        )
    else:
        console.print(f"  {champion['reason']}.")
        ml = [m for m in evaluation["models"] if not m["model_id"].startswith("B")]
        if ml:
            best = max(ml, key=lambda m: (m.get("holdout") or {}).get("skill", -1))
            h = best.get("holdout") or {}
            console.print(
                f"  best ML candidate: {best['label']}, "
                f"holdout skill {_pct(h.get('skill'), 2, True)}"
            )
        cov = hold.get("coverage")
        if cov is not None:
            console.print(f"  80% range contained the actual close {_pct(cov, 1)} of the time")


def _serve(ctx: RunContext, *, no_browser: bool, port: int | None) -> None:
    from nsefc.serve import NoResultsError, make_server, open_browser

    web = Path(__file__).resolve().parent / "web_dist"
    serve = ctx.settings.serve
    try:
        server = make_server(
            ctx.layout.api,
            web,
            host=serve.host,
            port=port or serve.port,
            port_tries=serve.port_tries,
        )
    except NoResultsError as exc:
        err.print(str(exc))
        raise typer.Exit(2) from exc
    except OSError as exc:
        err.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(2) from exc
    console.print()
    console.print(f"Serving at {server.url}  (Ctrl+C to stop)")
    if not no_browser:
        open_browser(server.url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("stopped")


# ---------------------------------------------------------------- commands
@app.command()
def run(
    no_serve: Annotated[
        bool, typer.Option("--no-serve", help="Stop after publishing (used by CI)")
    ] = False,
    profile: Profile = "default",
    sample: Sample = False,
    source_dir: SourceDir = None,
    force: Force = False,
    no_browser: NoBrowser = False,
    port: Port = None,
    verbose: Verbose = False,
) -> None:
    """All stages, then serve the app."""
    if sample and source_dir:
        err.print("[red]use either --sample or --source-dir, not both[/red]")
        raise typer.Exit(2)
    ctx = _context(sample=sample, profile=profile, force=force, verbose=verbose)
    started = time.monotonic()
    sweep_temporaries(ctx.layout.root)  # leftovers of an interrupted run
    outcomes: list[StageOutcome] = []
    try:
        outcomes.append(
            _stage(ctx, "acquire", lambda: stage_acquire(ctx, source_dir=source_dir, sample=sample))
        )
        outcomes.append(_stage(ctx, "ingest", lambda: stage_ingest(ctx)))
        _header(ctx)
        for outcome in outcomes:
            _line(outcome)
        for name, stage in (
            ("train", stage_train),
            ("predict", stage_predict),
            ("publish", stage_publish),
        ):
            outcome = _stage(ctx, name, lambda stage=stage: stage(ctx))  # type: ignore[misc]
            _line(outcome)
            outcomes.append(outcome)
    except StageError as exc:
        _write_run_record(ctx, outcomes, command="run", error=str(exc))
        raise _fail(exc) from exc
    _champion_summary(read_json(ctx.layout.reports / "evaluation.json"))
    console.print(
        f"\n[dim]Finished in {_seconds(time.monotonic() - started)}. "
        f"Reports: {ctx.layout.reports}[/dim]"
    )
    ctx.log("run", seconds=round(time.monotonic() - started, 1), profile=profile)
    _write_run_record(ctx, outcomes, command="run")
    if not no_serve:
        _serve(ctx, no_browser=no_browser, port=port)


def _write_run_record(
    ctx: RunContext, outcomes: list[StageOutcome], *, command: str, error: str | None = None
) -> None:
    from nsefc.pipeline.context import environment_summary, git_commit

    layout = ctx.layout
    record = {
        "run_id": ctx.run_id,
        "command": command,
        "profile": ctx.profile,
        "mode": ctx.mode,
        "environment": environment_summary(),
        "git_commit": git_commit(ctx.settings.project_root),
        "stages": {
            o.stage: {"cached": o.cached, "seconds": round(o.seconds, 2), "summary": o.summary}
            for o in outcomes
        },
        "stamps": {
            s: (st.as_dict() if (st := read_stamp(layout, s)) else None)
            for s in ("ingest", "train", "predict", "publish")
        },
        "outcome": "failed" if error else "succeeded",
        "error": error,
    }
    atomic_write_json(ctx.run_dir / "run.json", record)
    if error is None:
        atomic_write_json(layout.latest_run, {"run_id": ctx.run_id, "stamps": record["stamps"]})


@app.command()
def acquire(sample: Sample = False, source_dir: SourceDir = None) -> None:
    """Copy the dataset files into data/raw (or generate the sample)."""
    ctx = _context(sample=sample)
    try:
        _line(
            _stage(ctx, "acquire", lambda: stage_acquire(ctx, source_dir=source_dir, sample=sample))
        )
    except StageError as exc:
        raise _fail(exc) from exc


@app.command("ingest")
def ingest_command(force: Force = False) -> None:
    """Build the canonical panel and the data audit."""
    ctx = _context(force=force)
    try:
        _line(_stage(ctx, "ingest", lambda: stage_ingest(ctx)))
    except StageError as exc:
        raise _fail(exc) from exc


@app.command()
def train(profile: Profile = "default", force: Force = False, verbose: Verbose = False) -> None:
    """Walk-forward evaluation of every model, gates and champion selection."""
    ctx = _context(profile=profile, force=force, verbose=verbose)
    try:
        _line(_stage(ctx, "train", lambda: stage_train(ctx)))
    except StageError as exc:
        raise _fail(exc) from exc
    _champion_summary(read_json(ctx.layout.reports / "evaluation.json"))


@app.command()
def predict(force: Force = False) -> None:
    """Forecast the session after the last data date with the champion."""
    ctx = _context(force=force)
    try:
        _line(_stage(ctx, "predict", lambda: stage_predict(ctx)))
    except StageError as exc:
        raise _fail(exc) from exc


@app.command("publish")
def publish_command(force: Force = False) -> None:
    """Write the JSON files the app reads into data/api/v1."""
    ctx = _context(force=force)
    try:
        _line(_stage(ctx, "publish", lambda: stage_publish(ctx)))
    except StageError as exc:
        raise _fail(exc) from exc


@app.command()
def serve(no_browser: NoBrowser = False, port: Port = None) -> None:
    """Serve the app on 127.0.0.1."""
    _serve(_context(), no_browser=no_browser, port=port)


@app.command("import")
def import_command(
    file: Annotated[Path, typer.Argument(help="CSV with date, ticker, close, volume")],
) -> None:
    """Add sessions you collected after the dataset's last session."""
    from nsefc.acquire import Manifest, ManifestFile, read_manifest, write_manifest
    from nsefc.domain import SourceKind
    from nsefc.ingest import SchemaError, read_import_file

    ctx = _context(sample=False)
    layout = ctx.layout
    if not file.is_file():
        err.print(f"[red]{file} is not a file[/red]")
        raise typer.Exit(2)
    if not layout.ingest_report.is_file():
        err.print(
            "Run `uv run nsefc run` (or `nsefc ingest`) once before importing, so the dataset's "
            "last session is known."
        )
        raise typer.Exit(2)
    report = read_json(layout.ingest_report)
    if report["data_mode"] == "sample":
        err.print("Imports extend the real dataset; run without --sample first.")
        raise typer.Exit(2)
    digest = sha256_file(file)
    try:
        rows = read_import_file(file, sha256=digest, relative_name=file.name)
    except SchemaError as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(20) from exc
    last = date.fromisoformat(report["dataset_last_session"])
    early = rows[rows["session_date"].dt.date <= last]
    if len(early):
        err.print(
            f"[red]Rejected:[/red] {len(early)} row(s) on or before the dataset's last session "
            f"({last}); imports may only add later sessions."
        )
        raise typer.Exit(20)
    manifest_path = layout.imports / "manifest.json"
    manifest = (
        read_manifest(manifest_path)
        if manifest_path.is_file()
        else Manifest(source=SourceKind.USER_IMPORT, title="User imports")
    )
    existing_dates: set[date] = set()
    for entry in manifest.files:
        prior = read_import_file(
            layout.imports / entry.name, sha256=entry.sha256, relative_name=entry.name
        )
        existing_dates |= set(prior["session_date"].dt.date)
    overlap = sorted(set(rows["session_date"].dt.date) & existing_dates)
    if overlap:
        err.print(
            f"[red]Rejected:[/red] sessions already imported: {', '.join(map(str, overlap[:5]))}"
        )
        raise typer.Exit(20)
    target = layout.imports / f"{digest}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(file.read_bytes())
    files = [
        *manifest.files,
        ManifestFile(name=target.name, size=target.stat().st_size, sha256=digest),
    ]
    write_manifest(
        layout.imports, Manifest(source=SourceKind.USER_IMPORT, title="User imports", files=files)
    )
    console.print(
        f"Imported {len(rows)} rows for {rows['session_date'].dt.date.nunique()} session(s) "
        f"({rows['session_date'].min().date()} to {rows['session_date'].max().date()}). "
        "The next `nsefc run` picks them up."
    )


@app.command()
def status() -> None:
    """What is in data/: dataset, date range, last run, champion, headline metrics."""
    ctx = _context()
    layout = ctx.layout
    if not layout.ingest_report.is_file():
        console.print("No data yet. Run `uv run nsefc run`.")
        return
    report = read_json(layout.ingest_report)
    dataset = current_dataset(ctx, report)
    console.print(f"Data mode:  {report['data_mode']}")
    console.print(f"Dataset:    {dataset.get('citation') or dataset.get('title')}")
    console.print(
        f"Sessions:   {report['first_session']} to {report['last_session']} "
        f"({report['counts']['held_sessions']:,} held, "
        f"{report['counts']['missing_sessions']} missing)"
    )
    if layout.latest_run.is_file():
        console.print(f"Last run:   {read_json(layout.latest_run)['run_id']}")
    evaluation_path = layout.reports / "evaluation.json"
    if evaluation_path.is_file():
        _champion_summary(read_json(evaluation_path))
    if (layout.api / "status.json").is_file():
        console.print(f"\nPublished:  {read_json(layout.api / 'status.json')['release_id']}")


@app.command()
def clean(
    all_: Annotated[bool, typer.Option("--all", help="Also delete raw files")] = False,
) -> None:
    """Delete derived data (keeps raw files unless --all)."""
    layout = _context().layout
    targets = [
        layout.canonical,
        layout.features,
        layout.models,
        layout.predictions,
        layout.reports,
        layout.root / "api",
        layout.runs,
        layout.root / "stamps",
    ]
    if all_:
        targets.append(layout.raw)
    for target in targets:
        remove_tree(target)
    console.print(
        "Removed derived data" + (" and raw files" if all_ else "") + f" under {layout.root}"
    )


@app.callback(invoke_without_command=True)
def _version(
    version: Annotated[bool, typer.Option("--version", help="Print the version")] = False,
) -> None:
    if version:
        console.print(f"nsefc {__version__}")
        raise typer.Exit(0)


# ---------------------------------------------------------------- maintainer tools
@dev_app.command("web-hash")
def web_hash(
    write: Annotated[
        bool, typer.Option("--write", help="Record the hash in web_dist/.source-hash")
    ] = False,
    check: Annotated[
        bool, typer.Option("--check", help="Fail if the committed build is stale")
    ] = False,
) -> None:
    """SHA-256 over the frontend sources, to keep src/nsefc/web_dist in step."""
    from nsefc.devtools import HASH_FILE, committed_web_hash, web_source_hash

    root = _settings().project_root
    current = web_source_hash(root)
    if write:
        (root / HASH_FILE).parent.mkdir(parents=True, exist_ok=True)
        (root / HASH_FILE).write_text(current + "\n", encoding="utf-8")
    if check and committed_web_hash(root) != current:
        err.print(
            "The committed web build is stale: run `pnpm -C web build` and commit "
            "src/nsefc/web_dist"
        )
        raise typer.Exit(1)
    console.print(current)


@dev_app.command("update-readme")
def update_readme_command() -> None:
    """Insert the latest results between the README's results markers."""
    from nsefc.devtools import results_block, update_readme

    ctx = _context()
    evaluation_path = ctx.layout.reports / "evaluation.json"
    if not evaluation_path.is_file() or not ctx.layout.ingest_report.is_file():
        err.print("No results yet: run `uv run nsefc run --no-serve` first.")
        raise typer.Exit(2)
    if read_json(ctx.layout.ingest_report)["data_mode"] == "sample":
        err.print("Refusing to put sample-data results in the README; run on the real dataset.")
        raise typer.Exit(2)
    changed = update_readme(
        ctx.settings.project_root / "README.md",
        results_block(read_json(evaluation_path), read_json(ctx.layout.ingest_report)),
    )
    console.print("README updated" if changed else "README already up to date")


@dev_app.command("contract")
def contract_command(
    check: Annotated[
        bool, typer.Option("--check", help="Fail if committed schemas are stale")
    ] = False,
    validate: Annotated[
        Path | None, typer.Option("--validate", help="Validate every file under this api/v1 folder")
    ] = None,
) -> None:
    """Export the API contract's JSON Schema (or check it), and validate published files."""
    from nsefc.api.export import stale_schemas, validate_tree, write_schemas

    root = _settings().project_root
    out = root / "contracts" / "api" / "v1"
    if validate is not None:
        problems = validate_tree(validate)
        for problem in problems:
            err.print(problem)
        if problems:
            raise typer.Exit(40)
        console.print(f"all files under {validate} are valid")
        return
    if check:
        stale = stale_schemas(out)
        if stale:
            err.print("stale schemas: " + ", ".join(stale) + "; run `uv run nsefc dev contract`")
            raise typer.Exit(1)
        console.print("schemas are current")
        return
    for path in write_schemas(out):
        console.print(f"wrote {path.relative_to(root)}")


@dev_app.command("tune")
def tune_command(
    trials: Annotated[int, typer.Option("--trials", help="Optuna trials per model")] = 40,
    models: Annotated[
        str, typer.Option("--models", help="Comma-separated candidates")
    ] = "ridge,huber,lightgbm",
) -> None:
    """Tune the candidates on the tuning period only and print values to freeze in
    config/models/. Needs the full extra: `uv run --extra full nsefc dev tune`."""
    import yaml

    from nsefc.models import ModelUnavailable
    from nsefc.pipeline.stages import features_fingerprint
    from nsefc.pipeline.train import model_data, tune_candidates

    ctx = _context(verbose=True)
    ingest_stamp = read_stamp(ctx.layout, "ingest")
    if ingest_stamp is None or ctx.mode == "sample":
        err.print("Run `uv run nsefc run --no-serve` on the real dataset first.")
        raise typer.Exit(2)
    names = [m.strip() for m in models.split(",") if m.strip()]
    unknown = [m for m in names if m not in ctx.settings.model_specs]
    if unknown:
        err.print(f"[red]unknown model(s): {', '.join(unknown)}[/red]")
        raise typer.Exit(2)
    data = model_data(ctx, features_fingerprint(ctx, ingest_stamp.fingerprint))
    try:
        tuned = tune_candidates(ctx, data, names, trials)
    except ModelUnavailable as exc:
        err.print(f"[red]{exc}[/red]")
        raise typer.Exit(2) from exc
    report = ctx.layout.reports / "tuning.json"
    atomic_write_json(
        report,
        {
            "tuning_period": [str(d) for d in ctx.settings.periods.tuning],
            "trials": trials,
            "models": tuned,
        },
    )
    for model_id, params in tuned.items():
        console.print(f"\n# config/models/{model_id}.yaml, `frozen:`")
        console.print(yaml.safe_dump(params, sort_keys=False).rstrip())
    console.print(f"\n[dim]Saved to {report}[/dim]")


@dev_app.command("calendar")
def calendar_command(year: int) -> None:
    """List a year's weekday market closures."""
    ctx = _context(sample=False)
    for holiday in ctx.calendar.holidays(year):
        console.print(f"{holiday.date:%a %d %b %Y}  {holiday.name}  [{holiday.status}]")


def main() -> None:  # pragma: no cover - console entry point
    try:
        app()
    except KeyboardInterrupt:
        err.print("interrupted")
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    main()
