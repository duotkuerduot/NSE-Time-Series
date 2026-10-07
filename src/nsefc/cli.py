"""nsefc command-line entry points (Typer)."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer

from nsefc.config import ConfigError, Settings, load_settings, redacted, settings_hash
from nsefc.domain import Environment

if TYPE_CHECKING:
    from nsefc.ingestion.spike import Observation

app = typer.Typer(help="NSE daily forecast platform.", no_args_is_help=True, add_completion=False)
config_app = typer.Typer(help="Inspect and validate configuration.", no_args_is_help=True)
calendar_app = typer.Typer(help="Trading calendar.", no_args_is_help=True)
contract_app = typer.Typer(help="API contract: schemas and fixtures.", no_args_is_help=True)
spike_app = typer.Typer(help="Phase 0 source verification spike.", no_args_is_help=True)
data_app = typer.Typer(help="Historical data utilities.", no_args_is_help=True)
ingest_app = typer.Typer(help="Ingestion (Phase 2).", no_args_is_help=True)
for name, sub in [
    ("config", config_app),
    ("calendar", calendar_app),
    ("contract", contract_app),
    ("spike", spike_app),
    ("data", data_app),
    ("ingest", ingest_app),
]:
    app.add_typer(sub, name=name)

EnvOption = Annotated[str | None, typer.Option("--env", help="development|ci|dryrun|production")]
ConfigDir = Annotated[Path, typer.Option("--config-dir", help="Directory holding the YAML layers")]


def _settings(env: str | None, config_dir: Path) -> Settings:
    try:
        return load_settings(env, config_dir=config_dir)
    except ConfigError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=40) from exc


def _require_price_files(data_dir: Path) -> None:
    from nsefc.ingestion.providers.historical_file import price_files

    if not data_dir.is_dir() or not price_files(data_dir):
        typer.secho(
            f"no NSE_data_all_stocks_*.csv files under {data_dir}", fg=typer.colors.RED, err=True
        )
        raise typer.Exit(code=2)


def _calendar(settings: Settings):  # type: ignore[no-untyped-def]
    from nsefc.calendar import load_calendar

    return load_calendar(settings.calendar.holidays_file)


# ---------------------------------------------------------------------------- config
@config_app.command("show")
def config_show(env: EnvOption = None, config_dir: ConfigDir = Path("config")) -> None:
    """Print the resolved configuration (secrets redacted) and its hash."""
    settings = _settings(env, config_dir)
    typer.echo(json.dumps(redacted(settings), indent=2, sort_keys=True))
    typer.echo(f"config hash: {settings_hash(settings)}")


@config_app.command("validate")
def config_validate(config_dir: ConfigDir = Path("config")) -> None:
    """Load every environment's configuration; exit non-zero on the first problem."""
    for environment in Environment:
        _settings(environment.value, config_dir)
        typer.echo(f"ok  {environment.value}")


# ---------------------------------------------------------------------------- calendar
@calendar_app.command("holidays")
def calendar_holidays(
    year: int, env: EnvOption = None, config_dir: ConfigDir = Path("config")
) -> None:
    """List weekday market closures for a year."""
    calendar = _calendar(_settings(env, config_dir))
    for holiday in calendar.holidays(year):
        typer.echo(f"{holiday.date:%a %d %b %Y}  {holiday.name}  [{holiday.status}]")


@calendar_app.command("next-session")
def calendar_next(day: str, env: EnvOption = None, config_dir: ConfigDir = Path("config")) -> None:
    """The first session strictly after DAY (YYYY-MM-DD)."""
    calendar = _calendar(_settings(env, config_dir))
    typer.echo(calendar.next_session(date.fromisoformat(day)).isoformat())


@calendar_app.command("reconcile")
def calendar_reconcile(
    data_dir: Annotated[Path, typer.Option(help="Folder with the historical CSV files")] = Path(
        "NSE Data"
    ),
    out: Annotated[Path | None, typer.Option(help="Write a Markdown report here")] = None,
    env: EnvOption = None,
    config_dir: ConfigDir = Path("config"),
) -> None:
    """Compare the calendar with the dates that have trading data (ENGINEERING.md 7.5)."""
    from nsefc.pipeline.reports import calendar_reconciliation_markdown

    calendar = _calendar(_settings(env, config_dir))
    _require_price_files(data_dir)
    text = calendar_reconciliation_markdown(calendar, data_dir)
    if out:
        out.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {out}")
    else:
        typer.echo(text)


# ---------------------------------------------------------------------------- data
@data_app.command("profile")
def data_profile(
    data_dir: Annotated[Path, typer.Option(help="Folder with the historical CSV files")] = Path(
        "NSE Data"
    ),
    out: Annotated[Path | None, typer.Option(help="Write a Markdown report here")] = None,
) -> None:
    """Coverage profile of the historical dataset (feeds the Phase 1 audit)."""
    from nsefc.pipeline.reports import coverage_markdown

    _require_price_files(data_dir)
    text = coverage_markdown(data_dir)
    if out:
        out.write_text(text, encoding="utf-8")
        typer.echo(f"wrote {out}")
    else:
        typer.echo(text)


# ---------------------------------------------------------------------------- contract
@contract_app.command("export")
def contract_export(
    out: Annotated[Path, typer.Option(help="Schema output directory")] = Path("contracts/api/v1"),
    check: Annotated[bool, typer.Option(help="Fail if committed schemas are stale")] = False,
) -> None:
    """Export JSON Schema for every v1 resource."""
    from nsefc.api.export import stale_schemas, write_schemas

    if check:
        stale = stale_schemas(out)
        if stale:
            typer.secho(
                f"stale schemas: {', '.join(stale)}; run `nsefc contract export`",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)
        typer.echo("schemas are current")
        return
    for path in write_schemas(out):
        typer.echo(f"wrote {path}")


@contract_app.command("validate")
def contract_validate(
    root: Annotated[Path, typer.Option(help="An api/v1 root")] = Path("contracts/api/v1/fixtures"),
) -> None:
    """Validate every JSON file under an api/v1 root against the contract."""
    from nsefc.api.export import validate_tree

    problems = validate_tree(root)
    for problem in problems:
        typer.secho(problem, fg=typer.colors.RED, err=True)
    if problems:
        raise typer.Exit(code=1)
    typer.echo(f"all files under {root} are valid")


# ---------------------------------------------------------------------------- spike
def _parse_day(raw: str, option: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        message = f"{option} must be a date like 2026-01-02, got {raw!r}"
        typer.secho(message, fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from None


def _describe(o: Observation) -> str:
    if o.archive_failed:
        return f"available, but {o.error}"
    if o.available:
        return "available"
    detail = f"HTTP {o.status_code}" if o.status_code is not None else (o.error or "no response")
    return f"{o.outcome.replace('_', ' ')} ({detail}; {o.tried} URL(s) tried)"


def _spike_parts(settings: Settings, providers: list[str] | None):  # type: ignore[no-untyped-def]
    from nsefc.storage import open_store

    chosen = [
        p
        for p in settings.providers.registry
        if p.url_template and (p.provider_id in providers if providers else p.spike)
    ]
    if not chosen:
        typer.secho("no probe-able providers selected", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=40)
    return chosen, open_store(settings, "private")


@spike_app.command("probe")
def spike_probe(
    as_of: Annotated[
        str | None, typer.Option(help="Session date; default: latest closed session")
    ] = None,
    provider: Annotated[list[str] | None, typer.Option(help="Limit to these provider ids")] = None,
    store: Annotated[bool, typer.Option(help="Archive files to the private bucket")] = True,
    env: EnvOption = None,
    config_dir: ConfigDir = Path("config"),
) -> None:
    """Check whether each source has published the session yet, and archive what it has."""
    from nsefc.ingestion.spike import (
        PoliteClient,
        latest_probe_session,
        probe_session,
        save_observations,
    )

    settings = _settings(env, config_dir)
    calendar = _calendar(settings)
    session = (
        _parse_day(as_of, "--as-of") if as_of else latest_probe_session(calendar, datetime.now(UTC))
    )
    chosen, object_store = _spike_parts(settings, provider)
    file_store = object_store if store and settings.spike.store_files else None
    client = PoliteClient(settings.providers.politeness)
    archive_failures = 0
    try:
        for o in probe_session(client, chosen, session, file_store):
            save_observations(object_store, [o])  # saved one by one: a crash loses nothing
            archive_failures += o.archive_failed
            typer.echo(f"{o.provider_id:<14} {o.session_date}  {_describe(o)}")
    finally:
        client.close()
    if archive_failures:
        raise typer.Exit(code=1)


@spike_app.command("backcheck")
def spike_backcheck(
    start: Annotated[str, typer.Option("--from", help="First session date")],
    end: Annotated[str, typer.Option("--to", help="Last session date")],
    provider: Annotated[list[str] | None, typer.Option(help="Limit to these provider ids")] = None,
    store: Annotated[bool, typer.Option(help="Archive found files (a raw backfill)")] = False,
    env: EnvOption = None,
    config_dir: ConfigDir = Path("config"),
) -> None:
    """How far back does each archive reach? One polite request per session per source."""
    from nsefc.ingestion.spike import PoliteClient, backcheck, save_observations

    settings = _settings(env, config_dir)
    calendar = _calendar(settings)
    first, last = _parse_day(start, "--from"), _parse_day(end, "--to")
    chosen, object_store = _spike_parts(settings, provider)
    client = PoliteClient(settings.providers.politeness)
    unanswered = archive_failures = 0
    try:
        for definition in chosen:
            outcomes: Counter[str] = Counter()
            found = backcheck(
                client, calendar, definition, first, last, object_store if store else None
            )
            for o in found:
                save_observations(object_store, [o])  # saved one by one: a crash loses nothing
                outcomes[o.outcome] += 1
                archive_failures += o.archive_failed
            total = sum(outcomes.values())
            typer.echo(
                f"{definition.provider_id:<14} {outcomes['available']}/{total} available, "
                f"{outcomes['not_found']} not found, {outcomes['blocked']} blocked, "
                f"{outcomes['error']} errors"
            )
            unanswered += outcomes["blocked"] + outcomes["error"]
    finally:
        client.close()
    if unanswered:
        typer.secho(
            f"{unanswered} requests were blocked or failed: archive depth is unknown for those "
            "sessions, not zero",
            fg=typer.colors.YELLOW,
            err=True,
        )
    if archive_failures:
        raise typer.Exit(code=1)


@spike_app.command("report")
def spike_report(env: EnvOption = None, config_dir: ConfigDir = Path("config")) -> None:
    """Summarise observations: availability, archive reach and first-seen times (EAT)."""
    from nsefc.ingestion.spike import load_observations, summarise
    from nsefc.storage import open_store

    settings = _settings(env, config_dir)
    rows = summarise(load_observations(open_store(settings, "private")))
    if not rows:
        typer.echo("no observations yet; run `nsefc spike probe` after the close")
        return
    typer.echo(json.dumps(rows, indent=2))


# ---------------------------------------------------------------------------- ingest
@ingest_app.command("fetch")
def ingest_fetch() -> None:
    """Fetch, validate and commit new sessions (implemented in Phase 2, section 9.2)."""
    typer.secho(
        "ingest fetch is implemented in Phase 2; use `nsefc spike probe` for now",
        fg=typer.colors.YELLOW,
        err=True,
    )
    raise typer.Exit(code=1)


def main() -> None:  # pragma: no cover - console entry point
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
