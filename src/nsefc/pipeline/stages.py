"""The six stages and their caching (§1.1, §19).

Each stage declares its inputs, computes a fingerprint over them (file hashes, the relevant
settings and the package version), skips itself when its outputs exist with the same
fingerprint (unless ``--force``), writes outputs somewhere temporary before moving them into
place, and logs JSON lines to ``data/runs/<run_id>/log.jsonl``. A failed stage leaves earlier
outputs untouched, so a fixed rerun resumes where it stopped.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from nsefc.acquire import (
    AcquireError,
    AcquireResult,
    Manifest,
    acquire_dataset,
    acquire_local,
    acquire_sample,
    load_citation,
    read_active,
    read_manifest,
    write_active,
)
from nsefc.api.v1 import CONTRACT_VERSION
from nsefc.domain import SourceKind
from nsefc.evaluation import ModelData
from nsefc.ingest import CorrectionError, SchemaError, SourceFiles, ingest
from nsefc.models import ArtifactError, ModelUnavailable, load_artifact
from nsefc.pipeline.context import (
    RunContext,
    StageError,
    Stamp,
    code_hash,
    file_hash,
    read_stamp,
    utc_now,
    write_stamp,
)
from nsefc.pipeline.reports import data_audit_markdown, evaluation_markdown
from nsefc.pipeline.train import feature_spec, model_data, run_training
from nsefc.prediction import calibration_scores, forward_forecast
from nsefc.publishing import PublishError, PublishInputs, publish
from nsefc.quality import DataQualityError
from nsefc.storage import (
    atomic_write_json,
    atomic_write_text,
    read_json,
    read_table,
    staged_dir,
    write_table,
)

IMPORTS_MANIFEST = "manifest.json"


@dataclass(slots=True)
class StageOutcome:
    stage: str
    cached: bool
    seconds: float
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


def _cached(ctx: RunContext, stage: str, fingerprint: str, required: list[Path]) -> Stamp | None:
    stamp = read_stamp(ctx.layout, stage)
    if ctx.force or stamp is None or stamp.fingerprint != fingerprint:
        return None
    if not all(p.exists() for p in required):
        return None
    return stamp


def _finish(ctx: RunContext, stage: str, fingerprint: str, outputs: dict[str, Any]) -> Stamp:
    stamp = Stamp(stage, fingerprint, ctx.run_id, utc_now().isoformat(), outputs)
    write_stamp(ctx.layout, stamp)
    return stamp


def _rel(ctx: RunContext, path: Path) -> str:
    """A stamp output path, relative to the data folder so a moved clone keeps its cache."""
    try:
        return path.resolve().relative_to(ctx.layout.root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _out(ctx: RunContext, stamp: Stamp, key: str) -> Path:
    """Resolve a stamp output written by ``_rel`` (absolute paths from older stamps still work)."""
    value = Path(str(stamp.outputs[key]))
    return value if value.is_absolute() else ctx.layout.root.joinpath(*value.parts)


# ---------------------------------------------------------------- 1. acquire
def stage_acquire(
    ctx: RunContext, *, source_dir: Path | None = None, sample: bool = False
) -> StageOutcome:
    started = time.monotonic()
    raw = ctx.layout.raw
    try:
        if sample:
            result = acquire_sample(raw, ctx.calendar)
        elif source_dir is not None:
            result = acquire_local(raw, source_dir)
        else:
            citation = load_citation(ctx.settings.citation_file)
            result = acquire_dataset(raw, ctx.settings.project_root, citation)
    except AcquireError as exc:
        raise StageError(
            f"{exc}\nThe dataset ships in the repository's 'NSE Data' folder. Use "
            "`--source-dir PATH` for another folder of the same files, or `--sample` to try "
            "the app with synthetic data.",
            10,
        ) from exc
    write_active(raw, result)
    manifests = result.manifest_objects()
    files = sum(len(m.files) for m in manifests)
    ctx.log(
        "acquire",
        mode=result.mode,
        manifests=[str(p) for p in result.manifests],
        copied=result.copied,
    )
    summary = f"{files} files, {'copied' if result.copied else 'cached'}"
    return StageOutcome(
        "acquire", not result.copied, time.monotonic() - started, summary, {"mode": result.mode}
    )


def _sources(ctx: RunContext) -> tuple[AcquireResult, list[SourceFiles]]:
    try:
        active = read_active(ctx.layout.raw)
    except AcquireError as exc:
        raise StageError(str(exc), 2) from exc
    sources = [SourceFiles(read_manifest(p), p.parent) for p in active.manifests]
    imports = ctx.layout.imports / IMPORTS_MANIFEST
    if active.mode != "sample" and imports.is_file():
        sources.append(SourceFiles(read_manifest(imports), imports.parent))
    return active, sources


def current_dataset(ctx: RunContext, report: dict[str, Any]) -> dict[str, Any]:
    """DatasetInfo as shown to users: the ingest report's, with the latest attribution from
    reference/mendeley.yaml for the committed dataset, so a licence edit needs no re-ingest."""
    dataset = dict(report["dataset"])
    if dataset.get("source") == "mendeley":
        try:
            citation = load_citation(ctx.settings.citation_file)
        except AcquireError:
            return dataset
        dataset.update(
            title=citation.title,
            version=citation.version,
            licence=citation.licence,
            citation=citation.text,
            doi=citation.doi,
            url=f"https://doi.org/{citation.doi}" if citation.doi else citation.url,
        )
    return dataset


def _require_current_training(ctx: RunContext) -> Stamp:
    """The train stamp, if it was computed from the current data and settings."""
    layout = ctx.layout
    train = read_stamp(layout, "train")
    ingest = read_stamp(layout, "ingest")
    if train is None or ingest is None:
        raise StageError("no trained models yet: run `nsefc train` (or `nsefc run`) first", 2)
    profile = str(train.outputs.get("profile", ctx.profile))
    expected = train_fingerprint(ctx, features_fingerprint(ctx, ingest.fingerprint), profile)
    if train.fingerprint != expected:
        raise StageError(
            "the trained models are older than the data, settings or code: run `nsefc train` "
            "(or `nsefc run`) first",
            2,
        )
    return train


def dataset_info(sources: list[SourceFiles], first: str, last: str) -> dict[str, Any]:
    """DatasetInfo for status.json and the reports (contract v1.1)."""
    main = sources[0].manifest
    source = {"mendeley": "mendeley", "local": "local", "sample": "sample"}.get(
        main.source.value, "local"
    )
    return {
        "source": source,
        "title": main.title or "NSE daily prices",
        "version": main.version,
        "first_session": first,
        "last_session": last,
        "licence": main.licence,
        "citation": main.citation,
        "doi": main.doi,
        "url": f"https://doi.org/{main.doi}" if main.doi else None,
    }


# ---------------------------------------------------------------- 2. ingest
def ingest_fingerprint(ctx: RunContext, sources: list[SourceFiles]) -> str:
    s = ctx.settings
    return ctx.fingerprint(
        *sorted(f"{src.manifest.source.value}:{src.manifest.content_hash()}" for src in sources),
        file_hash(s.reference_dir / "corrections.yaml"),
        file_hash(s.reference_dir / "securities.csv"),
        file_hash(s.holidays_file),
        s.section_hash("quality"),
        code_hash("ingest"),
    )


def stage_ingest(ctx: RunContext) -> StageOutcome:
    started = time.monotonic()
    layout = ctx.layout
    _active, sources = _sources(ctx)
    fingerprint = ingest_fingerprint(ctx, sources)
    stamp = _cached(ctx, "ingest", fingerprint, [layout.bars, layout.ingest_report])
    if stamp:
        report = read_json(layout.ingest_report)
        return StageOutcome(
            "ingest", True, time.monotonic() - started, _ingest_summary(report), report
        )
    q = ctx.settings.quality
    try:
        result = ingest(
            sources,
            ctx.calendar,
            reference_dir=ctx.settings.reference_dir,
            band=q.band,
            event_threshold=q.event_threshold,
            mkt_window=q.mkt_window,
            mkt_min_share=q.mkt_min_share,
            vwap_tolerance=q.vwap_tolerance,
        )
    except (DataQualityError, SchemaError, CorrectionError) as exc:
        raise StageError(str(exc), 20) from exc
    report = result.report()
    report["dataset"] = dataset_info(sources, report["first_session"], report["last_session"])
    with staged_dir(layout.canonical) as staged:
        write_table(result.bars, staged / "bars.parquet")
        write_table(result.indices, staged / "indices.parquet")
        write_table(result.securities, staged / "securities.parquet")
        write_table(result.sessions, staged / "sessions.parquet")
        atomic_write_json(staged / "ingest_report.json", report)
    atomic_write_text(
        layout.reports / "data-audit.md",
        data_audit_markdown(report, citation=report["dataset"].get("citation")),
    )
    _finish(ctx, "ingest", fingerprint, {"report": _rel(ctx, layout.ingest_report)})
    ctx.log("ingest", counts=report["counts"])
    return StageOutcome(
        "ingest", False, time.monotonic() - started, _ingest_summary(report), report
    )


def _ingest_summary(report: dict[str, Any]) -> str:
    c = report["counts"]
    warnings = sum(
        1 for check in report["checks"] if check["severity"] == "warn" and check["count"]
    )
    corrections = c["corrections_applied"]
    return (
        f"{c['held_sessions']:,} sessions, {c['securities']} securities "
        f"({corrections} correction{'s' if corrections != 1 else ''} applied, "
        f"{warnings} warning{'s' if warnings != 1 else ''})"
    )


# ---------------------------------------------------------------- 3. train (and evaluate)
def features_fingerprint(ctx: RunContext, ingest_fp: str) -> str:
    s = ctx.settings
    return ctx.fingerprint(
        ingest_fp,
        s.section_hash("features", "universe", "intervals"),
        str(s.models.b1_window),
        code_hash("features"),
    )


def train_fingerprint(ctx: RunContext, features_fp: str, profile: str | None = None) -> str:
    s = ctx.settings
    return ctx.fingerprint(
        features_fp,
        profile or ctx.profile,
        s.section_hash(
            "periods",
            "evaluation",
            "intervals",
            "gates",
            "profiles",
            "models",
            "targets",
            "runtime",
            "model_specs",
            "baselines",
            "quality",
        ),
        code_hash("train"),
    )


def stage_train(ctx: RunContext) -> StageOutcome:
    started = time.monotonic()
    layout = ctx.layout
    ingest_stamp = read_stamp(layout, "ingest")
    if ingest_stamp is None or not layout.bars.is_file():
        raise StageError("no canonical data yet: run `nsefc ingest` (or `nsefc run`) first", 2)
    features_fp = features_fingerprint(ctx, ingest_stamp.fingerprint)
    fingerprint = train_fingerprint(ctx, features_fp)
    stamp = _cached(ctx, "train", fingerprint, [])
    if stamp and all(
        _out(ctx, stamp, k).is_file() for k in ("champion", "evaluation", "walkforward", "features")
    ):
        evaluation = read_json(_out(ctx, stamp, "evaluation"))
        return StageOutcome(
            "train", True, time.monotonic() - started, _train_summary(evaluation), evaluation
        )
    report = read_json(layout.ingest_report)
    data = model_data(ctx, features_fp)
    try:
        outputs = run_training(ctx, data, dataset_info=report["dataset"])
    except ModelUnavailable as exc:
        raise StageError(str(exc), 30) from exc
    evaluation = outputs.evaluation
    evaluation_path = layout.models / ctx.run_id / "evaluation.json"
    atomic_write_json(evaluation_path, evaluation)
    atomic_write_json(layout.reports / "evaluation.json", evaluation)
    atomic_write_text(layout.reports / "evaluation.md", evaluation_markdown(evaluation))
    _finish(
        ctx,
        "train",
        fingerprint,
        {
            "champion": _rel(ctx, outputs.champion_path),
            "walkforward": _rel(ctx, outputs.walkforward_path),
            "evaluation": _rel(ctx, evaluation_path),
            "features": _rel(ctx, layout.features / features_fp[:16] / "table.parquet"),
            "run_id": ctx.run_id,
            "profile": ctx.profile,
        },
    )
    ctx.log("train", champion=evaluation["champion"], seconds=evaluation["seconds"])
    return StageOutcome(
        "train", False, time.monotonic() - started, _train_summary(evaluation), evaluation
    )


def _train_summary(evaluation: dict[str, Any]) -> str:
    names = [m["model_id"] for m in evaluation["models"] if not m["model_id"].startswith("B")]
    baselines = sum(1 for m in evaluation["models"] if m["model_id"].startswith("B"))
    return f"{', '.join(names) or 'no ML models'}, {baselines} baselines"


# ---------------------------------------------------------------- 4. predict
def _predict_fingerprint(ctx: RunContext, train: Stamp) -> str:
    return ctx.fingerprint(
        train.fingerprint, file_hash(ctx.settings.holidays_file), code_hash("predict")
    )


def stage_predict(ctx: RunContext) -> StageOutcome:
    started = time.monotonic()
    layout = ctx.layout
    train = _require_current_training(ctx)
    fingerprint = _predict_fingerprint(ctx, train)
    out_dir = layout.predictions / train.outputs["run_id"]
    forecast_path, meta_path = out_dir / "forecast.parquet", out_dir / "forecast.json"
    stamp = _cached(ctx, "predict", fingerprint, [forecast_path, meta_path])
    if stamp:
        meta = read_json(meta_path)
        return StageOutcome(
            "predict", True, time.monotonic() - started, _predict_summary(meta), meta
        )
    evaluation = read_json(_out(ctx, train, "evaluation"))
    champion_id = evaluation["champion"]["model_id"]
    try:
        model = load_artifact(_out(ctx, train, "champion"))
    except ArtifactError as exc:
        raise StageError(f"refusing the champion artifact: {exc}", 30) from exc
    spec = feature_spec(ctx.settings)
    sessions = read_table(layout.sessions)
    held = pd.DatetimeIndex(sessions.loc[sessions["status"] == "held", "session_date"])
    data = ModelData(
        read_table(_out(ctx, train, "features")), spec.columns(), spec.categorical, held
    )
    walkforward = read_table(_out(ctx, train, "walkforward"))
    scores = calibration_scores(walkforward, champion_id, ctx.settings.intervals.calibration_window)
    origin = held[-1]
    target, known = ctx.calendar.next_session_or_weekday(origin.date())
    forecast = forward_forecast(
        data,
        model,
        scores=scores,
        level=ctx.settings.intervals.level,
        band=ctx.settings.quality.band,
        target=pd.Timestamp(target),
        target_from_calendar=known,
        max_lookback=ctx.settings.features.max_lookback,
    )
    write_table(forecast.rows, forecast_path)
    write_table(forecast.unavailable, out_dir / "forecast_unavailable.parquet")
    meta = {
        "origin": str(origin.date()),
        "target": str(target),
        "target_from_calendar": known,
        "champion": evaluation["champion"],
        "forecasts": len(forecast.rows),
        "unavailable": len(forecast.unavailable),
        "universe": sorted({*forecast.rows["ticker"], *forecast.unavailable["ticker"]}),
        "generated_at": utc_now().isoformat(),
    }
    atomic_write_json(meta_path, meta)
    _finish(
        ctx,
        "predict",
        fingerprint,
        {"forecast": _rel(ctx, forecast_path), "meta": _rel(ctx, meta_path)},
    )
    ctx.log("predict", forecasts=meta["forecasts"], target=meta["target"])
    return StageOutcome("predict", False, time.monotonic() - started, _predict_summary(meta), meta)


def _predict_summary(meta: dict[str, Any]) -> str:
    target = date.fromisoformat(meta["target"])
    label = target.strftime("%a %d %b %Y").replace(" 0", " ")
    return f"{meta['forecasts']} forecasts for {label}"


# ---------------------------------------------------------------- 5. publish
def stage_publish(ctx: RunContext, *, today: date | None = None) -> StageOutcome:
    started = time.monotonic()
    layout = ctx.layout
    train = _require_current_training(ctx)
    predict = read_stamp(layout, "predict")
    if predict is None or predict.fingerprint != _predict_fingerprint(ctx, train):
        raise StageError("no current forecast: run `nsefc predict` (or `nsefc run`) first", 2)
    # "Today" on the user's machine (§13.3): the local date, not the UTC one.
    today = today or datetime.now(UTC).astimezone().date()
    s = ctx.settings
    fingerprint = ctx.fingerprint(
        predict.fingerprint,
        file_hash(s.site_file),
        file_hash(s.citation_file),
        CONTRACT_VERSION,
        s.section_hash("publishing"),
        today.isoformat(),
        code_hash("publish"),
    )
    stamp = _cached(ctx, "publish", fingerprint, [layout.api / "status.json"])
    if stamp:
        return StageOutcome(
            "publish",
            True,
            time.monotonic() - started,
            f"{stamp.outputs['files']:,} files",
            stamp.outputs,
        )
    meta = read_json(_out(ctx, predict, "meta"))
    report = read_json(layout.ingest_report)
    run_dir = _out(ctx, predict, "forecast").parent
    inputs = PublishInputs(
        bars=read_table(layout.bars),
        securities=read_table(layout.securities),
        sessions=read_table(layout.sessions),
        indices=read_table(layout.indices),
        ingest_report=report,
        walkforward=read_table(_out(ctx, train, "walkforward")),
        evaluation=read_json(_out(ctx, train, "evaluation")),
        forecast=read_table(_out(ctx, predict, "forecast")),
        unavailable=read_table(run_dir / "forecast_unavailable.parquet"),
        forecast_meta=meta,
        universe=set(meta["universe"]),
        dataset=current_dataset(ctx, report),
        site_file=s.site_file,
        release_hash=fingerprint,
        generated_at=pd.Timestamp(meta["generated_at"]).to_pydatetime(),
        model_version=train.outputs["run_id"],
        today=today,
    )
    try:
        release_id, count = publish(inputs, s.publishing, layout.api)
    except PublishError as exc:
        raise StageError(str(exc), 40) from exc
    _finish(ctx, "publish", fingerprint, {"release_id": release_id, "files": count})
    ctx.log("publish", release_id=release_id, files=count)
    return StageOutcome(
        "publish",
        False,
        time.monotonic() - started,
        f"{count:,} files",
        {"release_id": release_id, "files": count},
    )


def manifest_source(manifest: Manifest) -> SourceKind:
    return manifest.source
