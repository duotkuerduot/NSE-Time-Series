"""Stage 2, ingest (§6): raw files -> the canonical panel in ``data/canonical/``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from nsefc.acquire import Manifest
from nsefc.calendar import TradingCalendar
from nsefc.domain import DataMode, InstrumentType, Severity, SourceKind
from nsefc.ingest.corrections import CorrectionReport, apply_corrections, load_corrections
from nsefc.ingest.panel import classify_sessions, synthesise
from nsefc.ingest.reader import (
    SchemaError,
    file_year,
    is_price_file,
    is_sector_file,
    read_price_file,
    read_sector_file,
)
from nsefc.ingest.securities import alias_map, build_securities, load_reference
from nsefc.quality.checks import (
    CheckResult,
    DataQualityError,
    dat01,
    dat02,
    dat03,
    errors,
    gap01,
    key01,
    mkt01,
    prc01,
    sch02,
    vol01,
)

VALUE_COLUMNS = ["name", "close", "previous", "low", "high", "volume", "turnover", "open"]


@dataclass(slots=True)
class SourceFiles:
    """A manifest and the folder its file names are relative to."""

    manifest: Manifest
    folder: Path


@dataclass(slots=True)
class IngestResult:
    bars: pd.DataFrame
    indices: pd.DataFrame
    securities: pd.DataFrame
    sessions: pd.DataFrame
    checks: list[CheckResult]
    corrections: CorrectionReport
    counts: dict[str, int] = field(default_factory=dict)
    data_mode: DataMode = DataMode.HISTORICAL
    dataset_last_session: pd.Timestamp | None = None

    def report(self) -> dict[str, Any]:
        sessions = self.sessions
        return {
            "data_mode": self.data_mode.value,
            "first_session": _iso(sessions["session_date"].min()),
            "last_session": _iso(sessions.loc[sessions["status"] == "held", "session_date"].max()),
            "dataset_last_session": _iso(self.dataset_last_session),
            "counts": self.counts,
            "checks": [c.as_dict() for c in self.checks],
            "corrections": [
                {
                    "id": a.rule.id,
                    "file": a.rule.file,
                    "action": a.rule.action,
                    "rows": a.rows,
                    "reason": a.rule.reason,
                }
                for a in self.corrections.applied
            ],
            "corrections_not_applicable": [r.id for r in self.corrections.not_applicable],
        }


def _iso(value: object) -> str | None:
    if value is None:
        return None
    stamp = pd.Timestamp(value)  # type: ignore[arg-type]
    return None if pd.isna(stamp) else stamp.date().isoformat()


def _read_sources(
    sources: list[SourceFiles],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, int], dict[str, int | None]]:
    frames, sectors = [], []
    counts = {"files": 0, "blank_rows": 0}
    years: dict[str, int | None] = {}
    unparsed: list[tuple[str, int, str]] = []
    for order, source in enumerate(sources):
        kind = source.manifest.source
        for entry, path in zip(
            source.manifest.files, source.manifest.file_paths(source.folder), strict=True
        ):
            if entry.name.lower().endswith(".zip"):
                continue
            label = entry.name
            if kind is SourceKind.USER_IMPORT:
                frame = read_import_file(path, sha256=entry.sha256, relative_name=label)
                years[label] = None
            elif is_price_file(entry.name):
                result = read_price_file(path, sha256=entry.sha256, relative_name=label)
                frame = result.rows
                counts["blank_rows"] += result.blank_rows
                unparsed.extend(result.unparsed_dates)
                years[label] = file_year(Path(entry.name).name)
            elif is_sector_file(entry.name):
                sector = read_sector_file(path)
                sector["file_order"] = (file_year(Path(entry.name).name) or 0) * 100 + order
                sectors.append(sector)
                continue
            else:
                continue
            frame["source"] = _source_label(source.manifest)
            frames.append(frame)
            counts["files"] += 1
    if unparsed:
        examples = ", ".join(f"{n}:{line} {text!r}" for n, line, text in unparsed[:5])
        raise SchemaError(f"SCH-01: {len(unparsed)} row(s) with an unreadable date ({examples})")
    if not frames:
        raise SchemaError("SCH-01: no NSE_data_all_stocks_*.csv price files in the acquired data")
    raw = pd.concat(frames, ignore_index=True)
    sector_frame = (
        pd.concat(sectors, ignore_index=True)
        if sectors
        else pd.DataFrame(columns=["code", "sector", "name", "file_order"])
    )
    return raw, sector_frame, counts, years


def _source_label(manifest: Manifest) -> str:
    if manifest.source is SourceKind.MENDELEY:
        return f"mendeley:{manifest.dataset_id}:v{manifest.version}"
    return manifest.source.value


def read_import_file(path: Path, *, sha256: str, relative_name: str) -> pd.DataFrame:
    """A user import (§5.5): date, ticker, close, volume and optional extra columns."""
    table = pd.read_csv(path, dtype=str, keep_default_na=False)
    table.columns = [c.strip().lower() for c in table.columns]
    required = {"date", "ticker", "close", "volume"}
    if not required <= set(table.columns):
        raise SchemaError(f"{relative_name}: an import needs columns {sorted(required)}")
    from nsefc.ingest.reader import parse_number

    def number(column: str) -> pd.Series:
        if column not in table.columns:
            return pd.Series(np.nan, index=table.index)
        return table[column].map(parse_number)

    out = pd.DataFrame(
        {
            "source_file": relative_name,
            "source_file_sha256": sha256,
            "line": np.arange(2, len(table) + 2),
            "session_date": pd.to_datetime(
                table["date"].str.strip(), format="%Y-%m-%d", errors="coerce"
            ),
            "code": table["ticker"].str.strip().str.upper(),
            "name": "",
            "close": number("close"),
            "previous": number("prev_close"),
            "low": number("low"),
            "high": number("high"),
            "volume": number("volume"),
            "turnover": number("turnover"),
            "open": number("open"),
        }
    )
    if out["session_date"].isna().any():
        bad = int(out["session_date"].isna().sum())
        raise SchemaError(f"{relative_name}: {bad} row(s) with a date that is not YYYY-MM-DD")
    return out


def ingest(
    sources: list[SourceFiles],
    calendar: TradingCalendar,
    *,
    reference_dir: Path,
    band: float,
    event_threshold: float,
    mkt_window: int,
    mkt_min_share: float,
    vwap_tolerance: float,
) -> IngestResult:
    raw, sectors_raw, counts, years = _read_sources(sources)
    counts["source_rows"] = len(raw)

    # 1. Documented corrections, keyed to file hashes (§6.4).
    corrections = load_corrections(reference_dir / "corrections.yaml")
    raw, correction_report = apply_corrections(raw, corrections)

    # 2. Index levels travel separately (^NASI and friends).
    is_index = raw["code"].str.startswith("^")
    indices = (
        raw[is_index][["session_date", "code", "close"]]
        .drop_duplicates(["session_date", "code"], keep="first")
        .rename(columns={"code": "index", "close": "level"})
        .sort_values(["index", "session_date"])
        .reset_index(drop=True)
    )
    rows = raw[~is_index].copy()

    # 3. Alias mapping: former tickers become current ones (§6.5).
    reference = load_reference(reference_dir / "securities.csv")
    aliases = alias_map(reference)
    rows["ticker"] = rows["code"].map(lambda c: aliases.get(c, c))
    sectors_raw = sectors_raw.assign(ticker=sectors_raw["code"].map(lambda c: aliases.get(c, c)))

    # 4. Identical duplicates are dropped automatically; conflicting ones fail KEY-01.
    rows["volume"] = rows["volume"].fillna(0)
    before = len(rows)
    rows = rows.drop_duplicates(["ticker", "session_date", *VALUE_COLUMNS], keep="first")
    counts["identical_duplicates_dropped"] = before - len(rows)

    checks: list[CheckResult] = []
    file_years = dict(years)
    checks.append(key01(rows))
    checks.append(dat01(rows))
    checks.append(dat03(rows, file_years))
    is_import = rows["source"] == SourceKind.USER_IMPORT.value
    dataset_last = rows.loc[~is_import, "session_date"].max()
    if is_import.any():
        overlap = rows[is_import & (rows["session_date"] <= dataset_last)]
        result = CheckResult(
            "IMP-01", "Imported sessions come after the dataset's last session", Severity.ERROR
        )
        result.count = len(overlap)
        result.examples = [
            f"{t} {d.date()}"
            for t, d in zip(overlap["ticker"], overlap["session_date"], strict=True)
        ][:12]
        checks.append(result)
    blocking = errors(checks)
    if blocking:
        raise DataQualityError(blocking)

    # 5. Row-level exclusions (SCH-02).
    bad, sch = sch02(rows)
    checks.insert(0, sch)
    rows = rows[~bad]
    untraded = rows["volume"] == 0
    rows.loc[untraded, ["high", "low"]] = np.nan  # an untraded session has no range

    # 6. Market-level checks on observed rows only, before any synthesis (MF-3).
    observed_counts = rows.groupby("session_date")["ticker"].nunique()
    first, last = rows["session_date"].min(), rows["session_date"].max()
    sessions, off_calendar = classify_sessions(observed_counts, calendar, first, last)
    checks.append(dat02(off_calendar))
    thin, mkt = mkt01(sessions, mkt_window, mkt_min_share)
    sessions["market_ok"] = ~thin
    checks.append(mkt)
    checks.append(gap01(sessions))

    # 7. Synthesis for held sessions only.
    held = pd.DatetimeIndex(sessions.loc[sessions["status"] == "held", "session_date"])
    rows = rows.rename(columns={"previous": "prev_close_reported"})
    names = rows[["ticker", "session_date", "name"]]
    panel = synthesise(
        rows[
            [
                "ticker",
                "session_date",
                "close",
                "prev_close_reported",
                "open",
                "high",
                "low",
                "volume",
                "turnover",
                "source",
                "source_file_sha256",
            ]
        ],
        held,
    )

    # 8. Events (PRC-01) and the VWAP consistency check.
    events, prc = prc01(panel, event_threshold)
    panel["is_event"] = events.to_numpy()
    checks.append(prc)
    checks.append(vol01(panel, vwap_tolerance))

    # 9. Securities.
    sectors = sectors_raw.rename(columns={"code": "source_code"})[
        ["ticker", "sector", "file_order"]
    ]
    securities = build_securities(panel, names, sectors, reference, dataset_last)
    types = securities.set_index("ticker")["instrument_type"]
    counts["securities"] = len(securities)
    counts["ordinary_shares"] = int((types == InstrumentType.ORDINARY.value).sum())
    counts["held_sessions"] = len(held)
    counts["missing_sessions"] = int((sessions["status"] == "missing").sum())
    counts["bars"] = len(panel)
    counts["carried_forward_rows"] = int(panel["is_carried_forward"].sum())
    counts["events"] = int(panel["is_event"].sum())
    counts["corrections_applied"] = len(correction_report.applied)
    counts["rows_corrected"] = sum(a.rows for a in correction_report.applied)
    counts["imported_rows"] = int(is_import.sum())

    bars = (
        panel[
            [
                "ticker",
                "session_date",
                "close",
                "prev_close_reported",
                "open",
                "high",
                "low",
                "volume",
                "turnover",
                "traded",
                "is_carried_forward",
                "is_event",
                "source",
                "source_file_sha256",
            ]
        ]
        .sort_values(["ticker", "session_date"])
        .reset_index(drop=True)
    )
    mode = DataMode.HISTORICAL_WITH_IMPORTS if is_import.any() else DataMode.HISTORICAL
    if any(s.manifest.source is SourceKind.SAMPLE for s in sources):
        mode = DataMode.SAMPLE
    return IngestResult(
        bars=bars,
        indices=indices,
        securities=securities,
        sessions=sessions,
        checks=checks,
        corrections=correction_report,
        counts=counts,
        data_mode=mode,
        dataset_last_session=dataset_last,
    )
