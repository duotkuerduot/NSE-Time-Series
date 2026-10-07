"""Generate the fixture release in contracts/api/v1/fixtures (illustrative values only).

Dates come from the real trading calendar; prices, volumes and forecasts are a seeded random
walk. Every file is built through the contract models, so the fixtures are valid by
construction, and `nsefc contract validate` re-checks them in CI.

    uv run python scripts/make_fixtures.py
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from pydantic import BaseModel

from nsefc.api import v1
from nsefc.calendar import load_calendar
from nsefc.domain import DirectionOutcome, UnavailableReason

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "contracts" / "api" / "v1" / "fixtures"
CALENDAR = load_calendar(ROOT / "config" / "calendar" / "nse_holidays.yaml")
SESSION = date(2026, 10, 7)
CHAMPION = v1.ModelRef(model_id="m_20261001_lgbm_7c1e9a", label="LightGBM", version="2026.10.1")

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


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    all_days = sessions(date(2021, 1, 4), SESSION)
    year_days = all_days[-250:]
    digest = hashlib.sha256(SESSION.isoformat().encode()).hexdigest()[:7]
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
        change_pct = round(last / prev - 1, 4)
        turnover = round(last * volumes[-1], 2)
        latest = v1.LatestSession(
            session=days[-1],
            close=last,
            prev_close=prev,
            change=round(last - prev, 2),
            change_pct=change_pct,
            volume=volumes[-1],
            turnover=turnover,
        )
        window = closes[-250:]
        write(
            v1.StockDetail(
                ticker=ticker,
                name=name,
                sector=sector,
                segment="Main Investment Market Segment",
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
        for label, cut_days in (("1y", 250), ("max", len(days))):
            write(
                v1.PriceHistory(
                    ticker=ticker,
                    range=label,
                    price_basis="vwap",
                    dates=days[-cut_days:],
                    close=closes[-cut_days:],
                    volume=volumes[-cut_days:],
                    events=[
                        v1.PriceEvent(date=days[-60], type="ex_dividend", label="Final dividend")
                    ]
                    if has_fc
                    else [],
                ),
                f"{base}/stocks/{ticker}/history.{label}.json",
            )

        if has_fc:
            history = []
            for i in range(len(days) - 61, len(days) - 1):
                origin, target = days[i], days[i + 1]
                pred_ret = rng.gauss(0, vol / 4)
                pred = round(closes[i] * (1 + pred_ret), 2)
                width = closes[i] * vol * 1.28
                lower, upper = round(pred - width, 2), round(pred + width, 2)
                actual = closes[i + 1]
                move, call = actual - closes[i], pred - closes[i]
                direction = (
                    DirectionOutcome.NO_CHANGE
                    if abs(call) / closes[i] < 0.001 or move == 0
                    else DirectionOutcome.HIT
                    if move * call > 0
                    else DirectionOutcome.MISS
                )
                history.append(
                    v1.PredictionHistoryRow(
                        origin_session=origin,
                        target_session=target,
                        predicted_close=pred,
                        lower=lower,
                        upper=upper,
                        actual_close=actual,
                        error_pct=round((pred - actual) / closes[i], 4),
                        direction=direction,
                        in_range=lower <= actual <= upper,
                        model_id=CHAMPION.model_id,
                    )
                )
            mae = sum(abs(r.error_pct or 0) for r in history) / len(history)
            naive = (
                sum(
                    abs(closes[i + 1] - closes[i]) / closes[i]
                    for i in range(len(days) - 61, len(days) - 1)
                )
                / 60
            )
            hits = [
                r for r in history if r.direction in (DirectionOutcome.HIT, DirectionOutcome.MISS)
            ]
            pred_ret = round(rng.gauss(0, vol / 4), 4)
            width = last * vol * 1.28
            forecast = v1.ForecastLatest(
                origin_session=SESSION,
                target_session=nxt,
                last_close=last,
                predicted_close=round(last * (1 + pred_ret), 2),
                predicted_return=pred_ret,
                range=v1.ForecastRange(
                    lower=round(last * (1 + pred_ret) - width, 2),
                    upper=round(last * (1 + pred_ret) + width, 2),
                ),
                model=CHAMPION,
                generated_at=datetime(2026, 10, 7, 15, 47, 55, tzinfo=UTC),
                data_through=SESSION,
                is_late=False,
            )
            prediction = v1.StockPrediction(
                ticker=ticker,
                latest=forecast,
                unavailable_reason=None,
                track_record=v1.TrackRecord(
                    basis="backtest",
                    window_sessions=60,
                    n=60,
                    mae_pct=round(mae, 4),
                    naive_mae_pct=round(naive, 4),
                    range_coverage=round(sum(bool(r.in_range) for r in history) / 60, 2),
                    directional_accuracy=round(
                        sum(r.direction == DirectionOutcome.HIT for r in hits) / len(hits), 2
                    )
                    if hits
                    else None,
                    directional_n=len(hits),
                ),
                history=list(reversed(history)),
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
        if status == "active" and turnover >= 100_000:
            movers.append(v1.Mover(ticker=ticker, name=name, close=last, change_pct=change_pct))
        latest_changes.append(change_pct)

    write(v1.StocksIndex(as_of_session=SESSION, items=items), f"{base}/stocks.json")

    nasi, _ = walk(rng, 125.0, 0.006, 250, 1.0)
    breadth_days = year_days[-60:]
    adv = [rng.randint(10, 30) for _ in breadth_days]
    dec = [rng.randint(10, 30) for _ in breadth_days]
    unc = [66 - a - d for a, d in zip(adv, dec, strict=True)]
    track_days = year_days[-60:]
    model_mae = [round(0.0125 + rng.gauss(0, 0.0005), 4) for _ in track_days]
    naive_mae = [round(m + 0.0008 + rng.gauss(0, 0.0003), 4) for m in model_mae]
    gainers = sorted((m for m in movers if m.change_pct > 0), key=lambda m: -m.change_pct)[:5]
    losers = sorted((m for m in movers if m.change_pct < 0), key=lambda m: m.change_pct)[:5]
    write(
        v1.MarketOverview(
            session=SESSION,
            summary=v1.MarketSummary(
                nasi=v1.IndexSummary(level=nasi[-1], change_pct=round(nasi[-1] / nasi[-2] - 1, 4)),
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
                    coverage_60=[round(0.79 + rng.gauss(0, 0.01), 3) for _ in track_days],
                    basis=["backtest"] * len(track_days),
                    model_label=[CHAMPION.label] * len(track_days),
                ),
            ),
        ),
        f"{base}/market/overview.json",
    )

    generated = datetime(2026, 10, 7, 15, 48, 12, tzinfo=UTC)
    write(
        v1.Status(
            release_id=release,
            generated_at=generated,
            latest_session=SESSION,
            next_session=nxt,
            stale_after=datetime.combine(nxt, datetime.min.time(), tzinfo=UTC)
            + timedelta(hours=19),
            pipeline=v1.PipelineStatus(
                status="succeeded",
                finished_at=generated,
                primary_source="nse_pricelist",
                fallback_used=False,
                dq="passed",
            ),
            champion=CHAMPION,
            notices=[
                v1.Notice(
                    code="FIXTURE",
                    message="Fixture data: values are illustrative, not market data.",
                    severity="warning",
                )
            ],
        ),
        "status.json",
    )
    print(f"wrote fixture release {release} to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
