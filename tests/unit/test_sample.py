"""The synthetic sample dataset (§16.3): deterministic, fictional, with planted defects."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from nsefc.calendar import TradingCalendar
from nsefc.ingest.corrections import load_corrections
from nsefc.ingest.reader import read_price_file
from nsefc.sample import generate
from nsefc.sample.generator import DUPLICATED_SESSION, GAP, MISDATED, RIGHTS, SPIKE, SPLIT
from nsefc.storage import sha256_file


def test_generation_is_byte_identical(tmp_path: Path, calendar: TradingCalendar) -> None:
    first = generate(tmp_path / "a", calendar)
    second = generate(tmp_path / "b", calendar)
    assert [p.name for p in first] == [p.name for p in second]
    assert [sha256_file(p) for p in first] == [sha256_file(p) for p in second]


def test_the_sample_correction_is_keyed_to_the_generated_file(
    tmp_path: Path, calendar: TradingCalendar, repo_root: Path
) -> None:
    """If this fails, the generator changed: update SAMPLE-01's sha256 in corrections.yaml."""
    paths = {p.name: p for p in generate(tmp_path, calendar)}
    rule = next(
        r
        for r in load_corrections(repo_root / "reference" / "corrections.yaml").corrections
        if r.id == "SAMPLE-01"
    )
    assert sha256_file(paths[f"NSE_data_all_stocks_{MISDATED[0].year}.csv"]) == rule.sha256


def test_planted_defects_are_present(tmp_path: Path, calendar: TradingCalendar) -> None:
    paths = generate(tmp_path, calendar)
    frames = [
        read_price_file(p, sha256="x" * 64, relative_name=p.name).rows
        for p in paths
        if p.name.startswith("NSE_data_all_stocks")
    ]
    rows = pd.concat(frames, ignore_index=True)
    days = set(rows["session_date"].dt.date)
    assert not any(GAP[0] <= d <= GAP[1] for d in days)  # the gap
    assert MISDATED[1] in days and MISDATED[0] not in days  # misdated block
    dup = rows[rows["session_date"].dt.date == DUPLICATED_SESSION]
    assert dup.duplicated(["code", "session_date"]).sum() == 3  # identical duplicates
    assert RIGHTS[0] in set(rows["code"])  # a rights line
    assert "^NASI" in set(rows["code"])
    tickers = sorted(c for c in set(rows["code"]) if c.startswith("SMPL") and not c.endswith("-R"))
    assert len(tickers) == 30 and all(t.startswith("SMPL") for t in tickers)  # fictional names
    for code, day in (SPLIT, SPIKE):
        series = (
            rows[rows["code"] == code]
            .sort_values("session_date")
            .set_index("session_date")["close"]
        )
        change = (series / series.shift(1) - 1).loc[pd.Timestamp(day)]
        assert abs(change) > 0.105, code  # band-breaching events
