"""Stage 5, publish: the static JSON files the web app reads.

Everything here works on finished tables (canonical data, walk-forward predictions, the
forecast and the evaluation summary) and never imports the ML layer. Each file is validated
against its contract model before it is written; the whole release is written to a
temporary folder and swapped into ``data/api/v1`` in one step, so the server never sees a
half-written release.
"""

from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel

from nsefc.api import v1
from nsefc.config import PublishingSettings
from nsefc.domain import UnavailableReason
from nsefc.storage import staged_dir

NASI, NSE20 = "^NASI", "^N20I"


class PublishError(RuntimeError):
    """A file failed contract validation (exit code 40)."""


@dataclass(slots=True)
class PublishInputs:
    bars: pd.DataFrame
    securities: pd.DataFrame
    sessions: pd.DataFrame
    indices: pd.DataFrame
    ingest_report: dict[str, Any]
    walkforward: pd.DataFrame  # out-of-sample predictions with intervals
    evaluation: dict[str, Any]
    forecast: pd.DataFrame  # champion forecasts at the last session
    unavailable: pd.DataFrame  # ticker, reason
    forecast_meta: dict[str, Any]  # origin, target, target_from_calendar, champion
    universe: set[str]  # forecast universe at the last session
    dataset: dict[str, Any]  # DatasetInfo fields
    site_file: Path
    release_hash: str
    generated_at: datetime
    model_version: str
    today: date


def _r(value: float, digits: int = 6) -> float:
    return float(round(float(value), digits))


def _price(value: float) -> float:
    return float(round(float(value), 2))


def _dump(model: BaseModel) -> bytes:
    return (
        json.dumps(model.model_dump(mode="json"), separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _validate(cls: type[BaseModel], payload: dict[str, Any], name: str) -> BaseModel:
    try:
        return cls.model_validate(payload)
    except ValueError as exc:
        raise PublishError(f"{name} fails the API contract: {exc}") from exc


def _iso(day: Any) -> str:
    return pd.Timestamp(day).date().isoformat()


def forecast_prices(last_close: float, point: float, lower: float, upper: float) -> dict[str, Any]:
    """The published prices of a forecast, from returns.

    Everything derives from the rounded last close, so the file always satisfies
    ``predicted_close == last_close x (1 + predicted_return)`` within rounding, whatever the
    precision of the source prices (imports may have more than two decimals).
    """
    close = _price(last_close)
    predicted = _price(close * (1 + point))
    return {
        "last_close": close,
        "predicted_close": predicted,
        "predicted_return": _r(point, 4),
        "range": {
            "level": 0.8,
            "lower": min(_price(close * (1 + lower)), predicted),
            "upper": max(_price(close * (1 + upper)), predicted),
        },
    }


def _load_site(path: Path, attribution: str) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
    data = data or {}
    return {
        "owner_name": str(data.get("owner_name", "")).strip() or "The maintainer",
        "tagline": str(data.get("tagline", "")).strip(),
        "links": [
            {"label": str(link["label"]), "url": str(link["url"])}
            for link in data.get("links") or []
        ],
        "attribution": attribution,
    }


class Publisher:
    def __init__(self, inputs: PublishInputs, settings: PublishingSettings) -> None:
        self.i = inputs
        self.s = settings
        bars = inputs.bars.sort_values(["ticker", "session_date"])
        self.bars = bars
        self.last_session = pd.Timestamp(
            inputs.sessions.loc[inputs.sessions["status"] == "held", "session_date"].max()
        )
        self.release_id = f"{self.last_session.date().isoformat()}.{inputs.release_hash[:12]}"
        champion = inputs.evaluation["champion"]
        self.model_ref = {
            "model_id": champion["model_id"],
            "label": champion["label"],
            "version": inputs.model_version,
        }
        self.files: dict[str, bytes] = {}

    # ------------------------------------------------------------------ helpers
    def add(self, relative: str, cls: type[BaseModel], payload: dict[str, Any]) -> None:
        self.files[relative] = _dump(_validate(cls, payload, relative))

    def release(self, relative: str) -> str:
        return f"r/{self.release_id}/{relative}"

    # ------------------------------------------------------------------ files
    def status(self) -> None:
        mode = self.i.ingest_report["data_mode"]
        notices = []
        if mode == "sample":
            notices.append(
                {
                    "code": "SAMPLE_DATA",
                    "message": "Showing synthetic sample data. "
                    "Run without --sample to use real NSE data.",
                    "severity": "info",
                }
            )
        if mode != "sample" and not self.i.dataset.get("licence"):
            notices.append(
                {
                    "code": "PERSONAL_USE",
                    "severity": "info",
                    "message": "The dataset's licence is not recorded here; "
                    "use the data for personal research.",
                }
            )
        self.add(
            "status.json",
            v1.Status,
            {
                "release_id": self.release_id,
                "generated_at": self.i.generated_at.isoformat(),
                "latest_session": _iso(self.last_session),
                "next_session": _iso(self.i.forecast_meta["target"]),
                "stale_after": None,
                "data_mode": mode,
                "dataset": self.i.dataset,
                "pipeline": {
                    "status": "succeeded",
                    "finished_at": self.i.generated_at.isoformat(),
                    "primary_source": self.i.dataset["source"],
                    "fallback_used": False,
                    "dq": "passed",
                },
                "champion": self.model_ref,
                "notices": notices,
            },
        )

    def _latest_rows(self) -> pd.DataFrame:
        bars = self.bars
        last = bars.groupby("ticker", sort=True).tail(1).set_index("ticker")
        prev = bars.groupby("ticker", sort=True).nth(-2).set_index("ticker")["close"]
        last["prev_close"] = prev.reindex(last.index)
        return last

    def stocks(self) -> None:
        latest = self._latest_rows()
        securities = self.i.securities.set_index("ticker")
        turnover = (
            self.bars.assign(t=self.bars["volume"] * self.bars["close"])
            .groupby("ticker")["t"]
            .apply(lambda s: float(s.tail(250).median()))
        )
        active = securities.index[securities["status"] == "active"]
        ranks = turnover.reindex(active).rank(ascending=False, method="first")
        items = []
        forecastable = set(self.i.forecast["ticker"])
        for key, row in securities.iterrows():
            ticker = str(key)
            last = cast(pd.Series, latest.loc[ticker])
            change = (
                (last["close"] / last["prev_close"] - 1) if pd.notna(last["prev_close"]) else 0.0
            )
            aliases = [
                a
                for a in (str(row["former_tickers"]) + "|" + str(row["former_names"])).split("|")
                if a
            ]
            items.append(
                {
                    "ticker": ticker,
                    "name": row["name"],
                    "sector": row["sector"]
                    if isinstance(row["sector"], str) and row["sector"]
                    else None,
                    "aliases": aliases,
                    "status": row["status"],
                    "has_forecast": ticker in forecastable,
                    "liquidity_rank": int(ranks[ticker])
                    if ticker in ranks.index and pd.notna(ranks[ticker])
                    else None,
                    "last": {"close": _price(last["close"]), "change_pct": _r(change)},
                }
            )
        self.add(
            self.release("stocks.json"),
            v1.StocksIndex,
            {
                "as_of_session": _iso(self.last_session),
                "items": items,
            },
        )

    def stock_files(self) -> None:
        securities = self.i.securities.set_index("ticker")
        forecast = self.i.forecast.set_index("ticker")
        unavailable = dict(
            zip(self.i.unavailable["ticker"], self.i.unavailable["reason"], strict=True)
        )
        holdout_start = pd.Timestamp(self.i.evaluation["periods"]["holdout"][0])
        champion_id = self.i.evaluation["champion"]["model_id"]
        wf = self.i.walkforward
        champ = wf[(wf["model_id"] == champion_id) & (wf["session_date"] >= holdout_start)]
        champ_by_ticker = dict(iter(champ.groupby("ticker")))
        holdout_sessions = int(champ["session_date"].nunique()) or 1
        for key, rows in self.bars.groupby("ticker", sort=True):
            ticker = str(key)
            sec = securities.loc[ticker]
            rows = rows.sort_values("session_date")
            last = rows.iloc[-1]
            prev = rows.iloc[-2] if len(rows) > 1 else None
            window = rows.tail(250)
            self.add(
                self.release(f"stocks/{ticker}.json"),
                v1.StockDetail,
                {
                    "ticker": ticker,
                    "name": sec["name"],
                    "sector": sec["sector"]
                    if isinstance(sec["sector"], str) and sec["sector"]
                    else None,
                    "segment": None,
                    "status": sec["status"],
                    "latest": {
                        "session": _iso(last["session_date"]),
                        "close": _price(last["close"]),
                        "prev_close": _price(prev["close"])
                        if prev is not None
                        else _price(last["close"]),
                        "change": _price(last["close"] - prev["close"])
                        if prev is not None
                        else 0.0,
                        "change_pct": _r(last["close"] / prev["close"] - 1)
                        if prev is not None
                        else 0.0,
                        "volume": int(last["volume"]),
                        "turnover": None,
                    },
                    "range_52w": {
                        "low": _price(window["close"].min()),
                        "high": _price(window["close"].max()),
                    },
                    "price_basis": "vwap",
                    "flags": {
                        "suspended": False,
                        "corporate_action_today": bool(last["is_event"]),
                        "ex_dividend_today": False,
                    },
                },
            )
            events = [
                {
                    "date": _iso(d),
                    "type": "large_move",
                    "label": "Move beyond the ±10% band: excluded from modelling",
                }
                for d in rows.loc[rows["is_event"], "session_date"]
            ]
            for name, part in (("1y", rows.tail(250)), ("max", rows)):
                part_events = [e for e in events if e["date"] >= _iso(part["session_date"].iloc[0])]
                self.add(
                    self.release(f"stocks/{ticker}/history.{name}.json"),
                    v1.PriceHistory,
                    {
                        "ticker": ticker,
                        "range": name,
                        "price_basis": "vwap",
                        "dates": [_iso(d) for d in part["session_date"]],
                        "close": [_price(c) for c in part["close"]],
                        "volume": [int(v) for v in part["volume"]],
                        "events": part_events,
                    },
                )
            self.add(
                self.release(f"stocks/{ticker}/prediction.json"),
                v1.StockPrediction,
                self._prediction(
                    ticker, forecast, unavailable, champ_by_ticker.get(ticker), holdout_sessions
                ),
            )

    def _prediction(
        self,
        ticker: str,
        forecast: pd.DataFrame,
        unavailable: dict[str, str],
        history: pd.DataFrame | None,
        holdout_sessions: int,
    ) -> dict[str, Any]:
        meta = self.i.forecast_meta
        latest: dict[str, Any] | None = None
        reason = None
        if ticker in forecast.index:
            f = cast(pd.Series, forecast.loc[ticker])
            target = pd.Timestamp(f["target_session"]).date()
            latest = {
                "origin_session": _iso(f["origin_session"]),
                "target_session": target.isoformat(),
                **forecast_prices(
                    float(f["last_close"]),
                    float(f["predicted_return"]),
                    float(f["return_lower"]),
                    float(f["return_upper"]),
                ),
                "model": self.model_ref,
                "generated_at": self.i.generated_at.isoformat(),
                "data_through": _iso(f["origin_session"]),
                "is_late": False,
                "target_in_past": target < self.i.today,
                "target_from_calendar": bool(meta["target_from_calendar"]),
            }
        else:
            reason = unavailable.get(ticker, UnavailableReason.NOT_IN_FORECAST_UNIVERSE.value)
        track = None
        rows: list[dict[str, Any]] = []
        if history is not None and len(history):
            h = history.sort_values("session_date")
            y, y_hat = h["y"].to_numpy(dtype=float), h["y_hat"].to_numpy(dtype=float)
            moved, called = y != 0, np.abs(y_hat) > 0.001
            calls = moved & called
            hits = np.sign(y_hat[calls]) == np.sign(y[calls])
            inside = (h["lower"] <= h["y"]) & (h["y"] <= h["upper"])
            track = {
                "basis": "backtest",
                "window_sessions": holdout_sessions,
                "n": len(h),
                "mae_pct": _r(np.mean(np.abs(y_hat - y))),
                "naive_mae_pct": _r(np.mean(np.abs(y))),
                "range_coverage": _r(inside.mean()),
                "directional_accuracy": _r(hits.mean()) if calls.any() else None,
                "directional_n": int(calls.sum()),
            }
            for _, r in h.tail(self.s.history_rows).iloc[::-1].iterrows():
                close = float(r["close"])
                actual = close * (1 + float(r["y"]))
                moved_r = float(r["y"]) != 0
                if not moved_r:
                    direction = "no_change"
                elif abs(float(r["y_hat"])) <= 0.001:
                    direction = None
                else:
                    direction = "hit" if np.sign(r["y_hat"]) == np.sign(r["y"]) else "miss"
                lower, upper = close * (1 + float(r["lower"])), close * (1 + float(r["upper"]))
                predicted = close * (1 + float(r["y_hat"]))
                rows.append(
                    {
                        "origin_session": _iso(r["session_date"]),
                        "target_session": _iso(r["target_session"]),
                        "predicted_close": _price(predicted),
                        "lower": _price(min(lower, predicted)),
                        "upper": _price(max(upper, predicted)),
                        "actual_close": _price(actual),
                        "error_pct": _r(float(r["y_hat"]) - float(r["y"])),
                        "direction": direction,
                        "in_range": bool(r["lower"] <= r["y"] <= r["upper"]),
                        "model_id": str(r["model_id"]),
                    }
                )
        return {
            "ticker": ticker,
            "latest": latest,
            "unavailable_reason": reason,
            "track_record": track,
            "history": rows,
        }

    def overview(self) -> None:
        bars = self.bars
        last_day = self.last_session
        today = bars[bars["session_date"] == last_day]
        securities = self.i.securities.set_index("ticker")
        ordinary = securities.index[securities["instrument_type"] == "ordinary"]
        today = today[today["ticker"].isin(ordinary)]
        prev_close = bars.groupby("ticker")["close"].shift(1).reindex(today.index)
        change = today["close"] / prev_close - 1
        traded_value = today["volume"] * today["close"]
        indices = self.i.indices

        def index_summary(code: str) -> dict[str, float] | None:
            series = indices[indices["index"] == code].sort_values("session_date")
            series = series[series["session_date"] <= last_day]
            if len(series) < 2 or series["session_date"].iloc[-1] != last_day:
                return None
            level, before = float(series["level"].iloc[-1]), float(series["level"].iloc[-2])
            return {"level": _r(level, 2), "change_pct": _r(level / before - 1)}

        # The same securities (ordinary shares) on both sides of turnover_vs_20d.
        ordinary_rows = bars[bars["ticker"].isin(ordinary)]
        daily_value = (
            ordinary_rows.assign(v=ordinary_rows["volume"] * ordinary_rows["close"])
            .groupby("session_date")["v"]
            .sum()
            .sort_index()
        )
        recent = daily_value[daily_value.index < last_day].tail(20)
        total = float(traded_value.sum())
        movers = pd.DataFrame(
            {
                "ticker": today["ticker"],
                "close": today["close"],
                "change": change,
                "value": traded_value,
            }
        )
        movers = movers[
            (movers["value"] >= self.s.movers_min_turnover_kes) & movers["change"].notna()
        ]
        names = securities["name"]

        def mover_list(frame: pd.DataFrame) -> list[dict[str, Any]]:
            return [
                {
                    "ticker": r.ticker,
                    "name": names[r.ticker],
                    "close": _price(cast(float, r.close)),
                    "change_pct": _r(cast(float, r.change)),
                }
                for r in frame.itertuples()
            ]

        gainers = movers[movers["change"] > 0].sort_values(
            ["change", "ticker"], ascending=[False, True]
        )
        losers = movers[movers["change"] < 0].sort_values(
            ["change", "ticker"], ascending=[True, True]
        )

        nasi = (
            indices[indices["index"] == NASI]
            .sort_values("session_date")
            .tail(self.s.index_trend_sessions)
        )
        held = self.i.sessions.loc[
            self.i.sessions["status"] == "held", "session_date"
        ].sort_values()
        breadth_days = held.tail(self.s.breadth_sessions)
        ordinary_bars = bars[bars["ticker"].isin(ordinary)].copy()
        ordinary_bars["chg"] = (
            ordinary_bars["close"] / ordinary_bars.groupby("ticker")["close"].shift(1) - 1
        )
        ordinary_bars = ordinary_bars[ordinary_bars["session_date"].isin(breadth_days)]
        adv = (ordinary_bars["chg"] > 0).groupby(ordinary_bars["session_date"]).sum()
        dec = (ordinary_bars["chg"] < 0).groupby(ordinary_bars["session_date"]).sum()
        unch = (ordinary_bars["chg"] == 0).groupby(ordinary_bars["session_date"]).sum()

        self.add(
            self.release("market/overview.json"),
            v1.MarketOverview,
            {
                "session": _iso(last_day),
                "summary": {
                    "nasi": index_summary(NASI),
                    "nse20": index_summary(NSE20),
                    "advancers": int((change > 0).sum()),
                    "decliners": int((change < 0).sum()),
                    "unchanged": int((change == 0).sum()),
                    "turnover_kes": _r(total, 0),
                    "turnover_vs_20d": _r(total / float(recent.mean()), 3)
                    if len(recent) and recent.mean() > 0
                    else None,
                },
                "movers": {
                    "min_turnover_kes": self.s.movers_min_turnover_kes,
                    "gainers": mover_list(gainers.head(self.s.movers_count)),
                    "losers": mover_list(losers.head(self.s.movers_count)),
                },
                "charts": {
                    "index_trend": {
                        "index": "NASI",
                        "dates": [_iso(d) for d in nasi["session_date"]],
                        "level": [_r(v, 2) for v in nasi["level"]],
                    },
                    "breadth": {
                        "dates": [_iso(d) for d in adv.index],
                        "advancers": [int(v) for v in adv],
                        "decliners": [int(v) for v in dec.reindex(adv.index)],
                        "unchanged": [int(v) for v in unch.reindex(adv.index)],
                    },
                    "track_record": self._track_series(),
                },
            },
        )

    def _track_series(self) -> dict[str, Any]:
        """Rolling 60-session miss of the champion vs the no-change guess, over the holdout."""
        wf = self.i.walkforward
        champion = self.i.evaluation["champion"]
        holdout_start = pd.Timestamp(self.i.evaluation["periods"]["holdout"][0])
        rows = wf[(wf["model_id"] == champion["model_id"]) & (wf["session_date"] >= holdout_start)]
        if rows.empty:
            return {
                "dates": [],
                "model_mae_pct_60": [],
                "naive_mae_pct_60": [],
                "coverage_60": [],
                "basis": [],
                "model_label": [],
            }
        daily = (
            rows.assign(
                em=np.abs(rows["y_hat"] - rows["y"]),
                eb=np.abs(rows["y"]),
                inside=((rows["lower"] <= rows["y"]) & (rows["y"] <= rows["upper"])).astype(float),
            )
            .groupby("session_date")[["em", "eb", "inside"]]
            .mean()
        )
        w = self.s.track_record_window
        rolled = daily.rolling(w, min_periods=w).mean().dropna()
        return {
            "dates": [_iso(d) for d in rolled.index],
            "model_mae_pct_60": [_r(v) for v in rolled["em"]],
            "naive_mae_pct_60": [_r(v) for v in rolled["eb"]],
            "coverage_60": [_r(v) for v in rolled["inside"]],
            "basis": ["backtest"] * len(rolled),
            "model_label": [champion["label"]] * len(rolled),
        }

    def report(self) -> None:
        ev = self.i.evaluation
        counts = self.i.ingest_report["counts"]

        def finite(value: Any) -> float | None:
            return _r(value) if isinstance(value, int | float) and math.isfinite(value) else None

        def scores(m: dict[str, Any] | None) -> dict[str, Any] | None:
            if not m:
                return None
            return {
                "mae": _r(m["mae"]),
                "mae_no_change": _r(m["mae_b0"]),
                "skill": _r(m["skill"]),
                "dm_p": finite(m["dm_p"]),
                "coverage": finite(m["coverage"]),
                "direction_accuracy": finite(m["direction"]["accuracy"]),
                "rows": int(m["rows"]),
                "securities": int(m["securities"]),
            }

        champion_id = ev["champion"]["model_id"]
        models = []
        headline = None
        for m in ev["models"]:
            by_year = {
                **m["selection"]["skill_by_year"],
                **((m.get("holdout") or {}).get("skill_by_year") or {}),
            }
            models.append(
                {
                    "model_id": m["model_id"],
                    "label": m["label"],
                    "is_champion": m["model_id"] == champion_id,
                    "selection": scores(m["selection"]),
                    "holdout": scores(m.get("holdout")),
                    "gates": [
                        {
                            "id": g["id"],
                            "name": g.get("name") or g["id"],
                            "passed": g["passed"],
                            "detail": g["detail"],
                        }
                        for g in m["gates"]
                    ],
                    "skill_by_year": {k: _r(v) for k, v in by_year.items() if math.isfinite(v)},
                }
            )
            if m["model_id"] == champion_id:
                headline = scores(m.get("holdout"))
        self.add(
            self.release("report.json"),
            v1.Report,
            {
                "profile": ev["profile"],
                "refit": ev["refit"],
                "periods": {
                    "selection": {
                        "start": ev["periods"]["selection"][0],
                        "end": ev["periods"]["selection"][1],
                    },
                    "holdout": {
                        "start": ev["periods"]["holdout"][0],
                        "end": ev["periods"]["holdout"][1],
                    },
                },
                "dataset": self.i.dataset,
                "universe": {
                    k: int(ev["universe"][k]) for k in ("min", "max", "median", "at_last_session")
                },
                "champion": ev["champion"],
                "headline": headline,
                "models": models,
                "data_audit": {
                    "sessions": int(counts["held_sessions"]),
                    "securities": int(counts["securities"]),
                    "corrections_applied": int(counts["corrections_applied"]),
                    "rows_corrected": int(counts["rows_corrected"]),
                    "duplicates_dropped": int(counts["identical_duplicates_dropped"]),
                    "missing_sessions": int(counts["missing_sessions"]),
                    "events_excluded": int(counts["events"]),
                    "carried_forward_rows": int(counts["carried_forward_rows"]),
                },
            },
        )

    def site(self) -> None:
        attribution = self.i.dataset.get("citation") or self.i.dataset["title"]
        self.add(self.release("site.json"), v1.Site, _load_site(self.i.site_file, attribution))

    def build(self) -> dict[str, bytes]:
        self.status()
        self.stocks()
        self.stock_files()
        self.overview()
        self.report()
        self.site()
        return self.files


def _previous_release(target: Path) -> str | None:
    """The release the current status.json points at, if it uses this contract version."""
    try:
        status = json.loads((target / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if status.get("contract_version") != v1.CONTRACT_VERSION:
        return None
    release = status.get("release_id")
    return release if isinstance(release, str) and (target / "r" / release).is_dir() else None


def publish(inputs: PublishInputs, settings: PublishingSettings, target: Path) -> tuple[str, int]:
    """Build, validate and atomically swap in the release. Returns (release_id, file count).

    The previous release is kept beside the new one, so a page that is already open keeps
    reading a complete release until it fetches the new status.json.
    """
    publisher = Publisher(inputs, settings)
    files = publisher.build()
    previous = _previous_release(target)
    with staged_dir(target) as staged:
        for relative, payload in files.items():
            path = staged.joinpath(*relative.split("/"))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
        if previous and previous != publisher.release_id:
            shutil.copytree(target / "r" / previous, staged / "r" / previous)
    return publisher.release_id, len(files)
