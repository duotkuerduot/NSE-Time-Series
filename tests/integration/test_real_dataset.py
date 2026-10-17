"""The real dataset in `NSE Data/` ingests to the documented panel (Phase 2 check, AC-05)."""

from __future__ import annotations

import pytest

from nsefc.pipeline.context import RunContext
from nsefc.pipeline.stages import stage_acquire, stage_ingest
from nsefc.storage import read_json
from tests.conftest import ROOT, settings_for

pytestmark = pytest.mark.skipif(
    not (ROOT / "NSE Data").is_dir(), reason="NSE Data is not in this checkout"
)


@pytest.fixture(scope="module")
def report(tmp_path_factory: pytest.TempPathFactory) -> dict:  # type: ignore[type-arg]
    data = tmp_path_factory.mktemp("real")
    ctx = RunContext(settings=settings_for(data, profile="default"), echo=lambda _m: None)
    stage_acquire(ctx)
    stage_ingest(ctx)
    return read_json(data / "canonical" / "ingest_report.json")  # type: ignore[no-any-return]


def test_counts_match_the_documented_findings(report: dict) -> None:  # type: ignore[type-arg]
    counts = report["counts"]
    assert (report["first_session"], report["last_session"]) == ("2007-01-02", "2026-06-30")
    assert counts["files"] == 20 and counts["source_rows"] == 301_124 and counts["blank_rows"] == 2
    # 155 missing sessions to Oct 2025, plus Nov-Dec 2025 between the 2025 and 2026 files.
    assert counts["held_sessions"] == 4_682 and counts["missing_sessions"] == 195
    assert counts["securities"] == 92 and counts["ordinary_shares"] == 75
    assert (
        counts["bars"] == 293_848
        and counts["carried_forward_rows"] == 12_661
        and counts["events"] == 416
    )
    assert counts["identical_duplicates_dropped"] == 64


def test_every_phase_0_defect_has_a_documented_rule(report: dict) -> None:  # type: ignore[type-arg]
    applied = {c["id"]: c["rows"] for c in report["corrections"]}
    assert applied == {"R2009-01": 40, "R2009-02": 59, "R2009-03": 59, "R2017-01": 70}
    checks = {c["id"]: c for c in report["checks"]}
    assert (
        checks["KEY-01"]["count"] == 0
        and checks["DAT-01"]["count"] == 0
        and checks["DAT-03"]["count"] == 0
    )
    assert checks["SCH-02"]["count"] == 1 and checks["MKT-01"]["count"] == 2
    assert checks["GAP-01"]["count"] == 195
    assert report["dataset"]["citation"].startswith("Wanjawa, Barack (2026)")
    assert report["data_mode"] == "historical"
