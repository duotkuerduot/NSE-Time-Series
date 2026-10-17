"""Generate the fixture release in contracts/api/v1/fixtures (illustrative values only).

Contract v1.1 (ENGINEERING.md §13.3). Dates come from the real trading calendar and mirror the
dataset's end (Fri 31 Oct 2025, forecast for Mon 3 Nov 2025); prices, volumes, forecasts and
evaluation results are a seeded random walk, not market data or real results. Every file is
built through the contract models, so the fixtures are valid by construction, and
`uv run nsefc dev contract --validate contracts/api/v1/fixtures` re-checks them in CI. The web
app's tests and its development server read these files.

    uv run python scripts/make_fixtures.py
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel

from nsefc.api import v1
from nsefc.calendar import load_calendar
from nsefc.domain import DirectionOutcome, UnavailableReason

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "contracts" / "api" / "v1" / "fixtures"
CALENDAR = load_calendar(ROOT / "config" / "calendar" / "nse_holidays.yaml")
SESSION = date(2025, 10, 31)
HOLDOUT_START = date(2023, 1, 3)
GENERATED = datetime(2026, 10, 16, 19, 15, 22, tzinfo=UTC)
CHAMPION = v1.ModelRef(model_id="lightgbm", label="LightGBM", version="20261016T191213Z")
CITATION = (
    'Wanjawa, Barack (2026), "Kenya Nairobi Securities Exchange (NSE) All Stocks Prices 2026", '
    "Mendeley Data, V1, doi: 10.17632/hvmhnp7f9r.1"
)
DATASET = v1.DatasetInfo(
    source="mendeley",
    title="Kenya Nairobi Securities Exchange (NSE) All Stocks Prices 2026",
    version=1,
    first_session=date(2007, 1, 2),
    last_session=SESSION,
    licence=None,
    citation=CITATION,
    doi="10.17632/hvmhnp7f9r.1",
    url="https://doi.org/10.17632/hvmhnp7f9r.1",
)

# ticker, name, sector, aliases, start price, daily vol, trade probability, status, forecast
STOCKS = [
    ("SCOM", "Safaricom PLC", "Telecommunication", [], 16.0, 0.016, 1.00, "active", True),
    ("EQTY", "Equity Group Holdings Plc", "Banking", [], 38.0, 0.014, 1.00, "active", True),
    ("KCB", "KCB Group Plc", "Banking", [], 30.0, 0.015, 1.00, "active", True),
    (
        "EABL",
        "East African Breweries PLC",
        "Manufacturing and Allied",
        [],
        140.0,
        0.012,
        0.98,
        "active",
        True,
    ),
    (
        "ABSA",
        "Absa Bank Kenya PLC",
        "Banking",
        ["Barclays Bank of Kenya"],
        11.0,
        0.011,
        0.97,
        "active",
        True,
    ),
    (
        "NCBA",
        "NCBA Group PLC",
        "Banking",
        ["NIC Group", "Commercial Bank of Africa"],
        35.0,
        0.012,
        0.95,
        "active",
        True,
    ),
    ("KUKZ", "Kakuzi Plc", "Agricultural", [], 390.0, 0.010, 0.31, "active", False),
    (
        "UCHM",
        "Uchumi Supermarket Plc",
        "Commercial and Services",
        [],
        0.3,
        0.02,
        0.0,
        "suspended",
        False,
    ),
]


def write(model: BaseModel, relative: str) -> None:
    path = OUT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(model.model_dump_json())
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sessions(start: date, end: date) -> list[date]:
    return CALENDAR.sessions_in(start, end)


def walk(rng: random.Random, start: float, vol: float, n: int, p_trade: float):  # type: ignore[no-untyped-def]
    closes, volumes, price = [], [], start
    for _ in range(n):
        traded = rng.random() < p_trade
        if traded:
            price = max(0.05, price * math.exp(rng.gauss(0.0003, vol)))
            volumes.append(int(rng.lognormvariate(12.5, 0.9)))
        else:
            volumes.append(0)
        closes.append(round(price, 2))
    return closes, volumes


def track(rng: random.Random, days: list[date], closes: list[float], vol: float):  # type: ignore[no-untyped-def]
    """Illustrative holdout-period forecasts with their actuals, oldest first."""
    rows = []
    start = next(i for i, d in enumerate(days) if d >= HOLDOUT_START)
    for i in range(start, len(days) - 1):
        origin, target = days[i], days[i + 1]
        pred_ret = rng.gauss(0, vol / 4)
        pred = round(closes[i] * (1 + pred_ret), 2)
        width = closes[i] * vol * 1.28
        lower, upper = round(pred - width, 2), round(pred + width, 2)
        actual = closes[i + 1]
        move, call = actual - closes[i], pred - closes[i]
        direction = (
            DirectionOutcome.NO_CHANGE
            if move == 0
            else None
            if abs(call) / closes[i] <= 0.001
            else DirectionOutcome.HIT
            if move * call > 0
            else DirectionOutcome.MISS
        )
        rows.append(
            v1.PredictionHistoryRow(
                origin_session=origin,
                target_session=target,
                predicted_close=pred,
                lower=min(lower, pred),
                upper=max(upper, pred),
                actual_close=actual,
                error_pct=round((pred - actual) / closes[i], 6),
                direction=direction,
                in_range=lower <= actual <= upper,
                model_id=CHAMPION.model_id,
            )
        )
    return rows


def scores(rng: random.Random, skill: float, *, rows: int, securities: int) -> v1.ReportScores:
    mae_b0 = round(0.0142 + rng.gauss(0, 0.0004), 6)
    return v1.ReportScores(
        mae=round(mae_b0 * (1 - skill), 6),
        mae_no_change=mae_b0,
        skill=round(skill, 6),
        dm_p=round(min(1.0, max(0.0, 0.5 - skill * 20)), 4),
        coverage=round(0.80 + rng.gauss(0, 0.01), 4),
        direction_accuracy=round(0.58 + rng.gauss(0, 0.01), 4),
        rows=rows,
        securities=securities,
    )


def report(rng: random.Random) -> v1.Report:
    """Illustrative evaluation results for the About page (not real results)."""
    years = [str(y) for y in range(2018, 2026)]
    specs = [
        ("B0", "No-change guess", 0.0, 0.0),
        ("B3", "AR(1) baseline", 0.004, 0.003),
        ("ridge", "Ridge regression", -0.012, -0.010),
        ("lightgbm", "LightGBM", 0.021, 0.017),
    ]
    models = []
    for model_id, label, sel_skill, hold_skill in specs:
        gates = (
            []
            if model_id == "B0"
            else [
                v1.ReportGate(
                    id="G-INT",
                    name="Integrity checks",
                    passed=True,
                    detail="artifact hash verified",
                ),
                v1.ReportGate(
                    id="G-SKILL",
                    name="Beats the no-change guess",
                    passed=sel_skill >= 0.01,
                    detail=f"skill {sel_skill:+.2%} (needs >= 1%)",
                ),
                v1.ReportGate(
                    id="G-BASE",
                    name="Beats the simple baselines",
                    passed=model_id in ("B3", "lightgbm"),
                    detail="vs B3",
                ),
                v1.ReportGate(
                    id="G-STAB",
                    name="Stable from year to year",
                    passed=sel_skill > 0,
                    detail="positive in 4 of 5 years",
                ),
                v1.ReportGate(
                    id="G-DIR",
                    name="Direction no worse than simple rules",
                    passed=True,
                    detail="not worse than the best trivial rule",
                ),
                v1.ReportGate(
                    id="G-CAL",
                    name="80% range is calibrated",
                    passed=True,
                    detail="80% range contained the actual close 80.4% of the time",
                ),
                v1.ReportGate(
                    id="G-HOLD",
                    name="Confirmed on the holdout period",
                    passed=hold_skill > 0 and hold_skill >= sel_skill / 2,
                    detail=f"holdout skill {hold_skill:+.2%}",
                ),
            ]
        )
        models.append(
            v1.ReportModel(
                model_id=model_id,
                label=label,
                is_champion=model_id == CHAMPION.model_id,
                selection=scores(rng, sel_skill, rows=21_480, securities=24),
                holdout=scores(rng, hold_skill, rows=14_210, securities=26),
                gates=gates,
                skill_by_year={
                    y: round(sel_skill + rng.gauss(0, 0.004), 6) if model_id != "B0" else 0.0
                    for y in years
                },
            )
        )
    headline = next(m.holdout for m in models if m.is_champion)
    return v1.Report(
        profile="default",
        refit="quarterly",
        periods=v1.ReportPeriods(
            selection=v1.ReportPeriod(start=date(2018, 1, 1), end=date(2022, 12, 31)),
            holdout=v1.ReportPeriod(start=date(2023, 1, 1), end=date(2025, 10, 30)),
        ),
        dataset=DATASET,
        universe=v1.ReportUniverse(min=16, max=29, median=20, at_last_session=26),
        champion=v1.ReportChampion(
            model_id=CHAMPION.model_id,
            label=CHAMPION.label,
            reason="LightGBM passed every gate with the lowest selection-period miss",
        ),
        headline=headline,
        models=models,
        data_audit=v1.DataAudit(
            sessions=4560,
            securities=88,
            corrections_applied=4,
            rows_corrected=228,
            duplicates_dropped=64,
            missing_sessions=155,
            events_excluded=395,
            carried_forward_rows=12661,
        ),
    )


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    all_days = sessions(date(2021, 1, 4), SESSION)
    year_days = all_days[-250:]
    digest = hashlib.sha256(SESSION.isoformat().encode()).hexdigest()[:12]
    release = f"{SESSION.isoformat()}.{digest}"
    base = f"r/{release}"
    nxt = CALENDAR.next_session(SESSION)
    rng = random.Random(20261007)

    items, movers, latest_changes = [], [], []
    for rank, (ticker, name, sector, aliases, start, vol, p_trade, status, has_fc) in enumerate(
        STOCKS, start=1
    ):
        closes, volumes = walk(rng, start, vol, len(all_days), p_trade)
        if status == "suspended":
            cut = len(all_days) - 45
            closes, volumes, days = closes[:cut], volumes[:cut], all_days[:cut]
        else:
            days = all_days
        last, prev = closes[-1], closes[-2]
        change_pct = round(last / prev - 1, 6)
        latest = v1.LatestSession(
            session=days[-1],
            close=last,
            prev_close=prev,
            change=round(last - prev, 2),
            change_pct=change_pct,
            volume=volumes[-1],
            turnover=None,
        )
        window = closes[-250:]
        write(
            v1.StockDetail(
                ticker=ticker,
                name=name,
                sector=sector,
                segment=None,
                status=status,
                latest=latest,
                range_52w=v1.Range52w(low=min(window), high=max(window)),
                price_basis="vwap",
                flags=v1.StockFlags(
                    suspended=status == "suspended",
                    corporate_action_today=False,
                    ex_dividend_today=False,
                ),
            ),
            f"{base}/stocks/{ticker}.json",
        )
        event = v1.PriceEvent(
            date=days[-60],
            type="large_move",
            label="Move beyond the ±10% band: excluded from modelling",
        )
        for label, cut_days in (("1y", 250), ("max", len(days))):
            write(
                v1.PriceHistory(
                    ticker=ticker,
                    range=label,
                    price_basis="vwap",
                    dates=days[-cut_days:],
                    close=closes[-cut_days:],
                    volume=volumes[-cut_days:],
                    events=[event] if has_fc else [],
                ),
                f"{base}/stocks/{ticker}/history.{label}.json",
            )

        if has_fc:
            rows = track(rng, days, closes, vol)
            holdout = days[next(i for i, d in enumerate(days) if d >= HOLDOUT_START) + 1 :]
            mae = sum(abs(r.error_pct or 0) for r in rows) / len(rows)
            naive = sum(
                abs((r.actual_close or 0) - c) / c
                for r, c in zip(rows, closes[len(closes) - len(rows) - 1 : -1], strict=True)
            ) / len(rows)
            calls = [
                r for r in rows if r.direction in (DirectionOutcome.HIT, DirectionOutcome.MISS)
            ]
            pred_ret = round(rng.gauss(0, vol / 4), 4)
            width = last * vol * 1.28
            predicted = round(last * (1 + pred_ret), 2)
            forecast = v1.ForecastLatest(
                origin_session=SESSION,
                target_session=nxt,
                last_close=last,
                predicted_close=predicted,
                predicted_return=pred_ret,
                range=v1.ForecastRange(
                    lower=round(predicted - width, 2), upper=round(predicted + width, 2)
                ),
                model=CHAMPION,
                generated_at=GENERATED,
                data_through=SESSION,
                is_late=False,
                target_in_past=True,
                target_from_calendar=True,
            )
            prediction = v1.StockPrediction(
                ticker=ticker,
                latest=forecast,
                unavailable_reason=None,
                track_record=v1.TrackRecord(
                    basis="backtest",
                    window_sessions=len(holdout),
                    n=len(rows),
                    mae_pct=round(mae, 6),
                    naive_mae_pct=round(naive, 6),
                    range_coverage=round(sum(bool(r.in_range) for r in rows) / len(rows), 6),
                    directional_accuracy=round(
                        sum(r.direction == DirectionOutcome.HIT for r in calls) / len(calls), 6
                    )
                    if calls
                    else None,
                    directional_n=len(calls),
                ),
                history=list(reversed(rows))[:60],
            )
        else:
            reason = (
                UnavailableReason.SUSPENDED
                if status == "suspended"
                else UnavailableReason.NOT_IN_FORECAST_UNIVERSE
            )
            prediction = v1.StockPrediction(
                ticker=ticker, latest=None, unavailable_reason=reason, track_record=None, history=[]
            )
        write(prediction, f"{base}/stocks/{ticker}/prediction.json")

        items.append(
            v1.StockIndexItem(
                ticker=ticker,
                name=name,
                sector=sector,
                aliases=aliases,
                status=status,
                has_forecast=has_fc,
                liquidity_rank=rank,
                last=v1.LastPrice(close=last, change_pct=change_pct),
            )
        )
        if status == "active" and last * volumes[-1] >= 100_000:
            movers.append(v1.Mover(ticker=ticker, name=name, close=last, change_pct=change_pct))
        latest_changes.append(change_pct)

    write(v1.StocksIndex(as_of_session=SESSION, items=items), f"{base}/stocks.json")

    nasi, _ = walk(rng, 125.0, 0.006, 250, 1.0)
    breadth_days = year_days[-60:]
    adv = [rng.randint(10, 30) for _ in breadth_days]
    dec = [rng.randint(10, 30) for _ in breadth_days]
    unc = [66 - a - d for a, d in zip(adv, dec, strict=True)]
    track_days = year_days[-60:]
    model_mae = [round(0.0125 + rng.gauss(0, 0.0005), 6) for _ in track_days]
    naive_mae = [round(m + 0.0008 + rng.gauss(0, 0.0003), 6) for m in model_mae]
    gainers = sorted((m for m in movers if m.change_pct > 0), key=lambda m: -m.change_pct)[:5]
    losers = sorted((m for m in movers if m.change_pct < 0), key=lambda m: m.change_pct)[:5]
    write(
        v1.MarketOverview(
            session=SESSION,
            summary=v1.MarketSummary(
                nasi=v1.IndexSummary(level=nasi[-1], change_pct=round(nasi[-1] / nasi[-2] - 1, 6)),
                nse20=v1.IndexSummary(level=2384.5, change_pct=-0.0012),
                advancers=sum(c > 0 for c in latest_changes),
                decliners=sum(c < 0 for c in latest_changes),
                unchanged=sum(c == 0 for c in latest_changes),
                turnover_kes=612_400_000,
                turnover_vs_20d=1.18,
            ),
            movers=v1.Movers(min_turnover_kes=100_000, gainers=gainers, losers=losers),
            charts=v1.MarketCharts(
                index_trend=v1.IndexTrend(index="NASI", dates=year_days, level=nasi),
                breadth=v1.Breadth(dates=breadth_days, advancers=adv, decliners=dec, unchanged=unc),
                track_record=v1.TrackRecordSeries(
                    dates=track_days,
                    model_mae_pct_60=model_mae,
                    naive_mae_pct_60=naive_mae,
                    coverage_60=[round(0.79 + rng.gauss(0, 0.01), 6) for _ in track_days],
                    basis=["backtest"] * len(track_days),
                    model_label=[CHAMPION.label] * len(track_days),
                ),
            ),
        ),
        f"{base}/market/overview.json",
    )
    write(report(rng), f"{base}/report.json")
    write(
        v1.Site(
            owner_name="Duot Kuer",
            tagline="Built by Duot Kuer",
            links=[v1.SiteLink(label="GitHub", url="https://github.com/duotkuerduot")],
            attribution=CITATION,
        ),
        f"{base}/site.json",
    )
    write(
        v1.Status(
            release_id=release,
            generated_at=GENERATED,
            latest_session=SESSION,
            next_session=nxt,
            stale_after=None,
            data_mode="historical",
            dataset=DATASET,
            pipeline=v1.PipelineStatus(
                status="succeeded",
                finished_at=GENERATED,
                primary_source="mendeley",
                fallback_used=False,
                dq="passed",
            ),
            champion=CHAMPION,
            notices=[
                v1.Notice(
                    code="FIXTURE",
                    message="Fixture data: values are illustrative, not market data.",
                    severity="warning",
                ),
                v1.Notice(
                    code="PERSONAL_USE",
                    message=(
                        "The dataset's licence is not recorded here; "
                        "use the data for personal research."
                    ),
                    severity="info",
                ),
            ],
        ),
        "status.json",
    )
    print(f"wrote fixture release {release} to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
