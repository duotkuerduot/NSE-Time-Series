"""API contract v1.1: every static file the frontend reads.

These models validate every published file before it is written, export JSON Schema to
``contracts/api/v1`` and generate the frontend's TypeScript types, so the two sides cannot
drift apart silently. v1.1 (the local tool) adds ``data_mode`` and ``dataset`` to the
status, makes ``stale_after`` nullable, adds ``target_in_past`` and ``target_from_calendar``
to the latest forecast, and adds ``report.json`` and ``site.json``.
"""

from __future__ import annotations

from datetime import date
from itertools import pairwise
from typing import Annotated, Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from nsefc.domain import DirectionOutcome, UnavailableReason

API_VERSION: Final = "1"
CONTRACT_VERSION: Final = "1.1"
Ticker = Annotated[str, Field(pattern=r"^[A-Z0-9&.\-]{2,12}$", description="NSE ticker, e.g. SCOM")]
Fraction = Annotated[float, Field(description="A ratio, e.g. 0.0124 for 1.24%")]
ErrorSize = Annotated[float, Field(ge=0, description="An average absolute error, e.g. 0.0124")]
Share = Annotated[float, Field(ge=0, le=1, description="A share of cases, e.g. 0.8 for 80%")]
# Timestamps carry an offset ("...Z"): a browser reads a bare one as the viewer's local time.
Timestamp = Annotated[AwareDatetime, Field(description="ISO 8601 with offset, e.g. ...Z")]
Kes = Annotated[float, Field(ge=0, description="Kenya shillings")]
PriceKes = Annotated[float, Field(gt=0, description="Price in Kenya shillings")]
ReleaseId = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}\.[0-9a-f]{7,64}$")]


class _Resource(BaseModel):
    # Every published file carries every field, so defaults are still required in the schema.
    model_config = ConfigDict(
        extra="forbid", frozen=True, json_schema_serialization_defaults_required=True
    )


def _same_length(where: str, **series: list[object]) -> None:
    lengths = {name: len(values) for name, values in series.items()}
    if len(set(lengths.values())) > 1:
        raise ValueError(f"{where}: series lengths differ {lengths}")


def _ascending(where: str, dates: list[date]) -> None:
    if any(b <= a for a, b in pairwise(dates)):
        raise ValueError(f"{where}: dates must be strictly ascending")


# ---------------------------------------------------------------------------- shared parts
class ModelRef(_Resource):
    model_id: str
    label: str = Field(description="Display name, e.g. 'LightGBM' or 'No-change baseline'")
    version: str


class Notice(_Resource):
    code: str
    message: str
    severity: Literal["info", "warning"] = "info"


# ---------------------------------------------------------------------------- /v1/status
class PipelineStatus(_Resource):
    status: Literal[
        "succeeded", "failed", "running", "data_not_yet_available", "quarantined", "skipped"
    ]
    finished_at: Timestamp | None
    primary_source: Literal["mendeley", "local", "sample"]
    fallback_used: bool = Field(description="Always false in local mode")
    dq: Literal["passed", "held", "failed", "not_run"]


class DatasetInfo(_Resource):
    """Where the data came from, for the header, footer and About page (v1.1)."""

    source: Literal["mendeley", "local", "sample"]
    title: str
    version: int | None
    first_session: date
    last_session: date
    licence: str | None
    citation: str | None
    doi: str | None
    url: str | None


class Status(_Resource):
    """Pointer to the current release, plus run and data status."""

    api_version: Literal["1"] = API_VERSION
    contract_version: Literal["1.1"] = CONTRACT_VERSION
    release_id: ReleaseId
    generated_at: Timestamp
    latest_session: date
    next_session: date
    stale_after: Timestamp | None = Field(
        description="When the next release is due; null in local mode, where data is never late"
    )
    data_mode: Literal["historical", "historical+imports", "sample"]
    dataset: DatasetInfo
    pipeline: PipelineStatus
    champion: ModelRef | None
    notices: list[Notice] = Field(default_factory=list)

    @model_validator(mode="after")
    def _order(self) -> Status:
        if self.next_session <= self.latest_session:
            raise ValueError("next_session must come after latest_session")
        return self


# ---------------------------------------------------------------------------- /v1/stocks
class LastPrice(_Resource):
    close: PriceKes
    change_pct: Fraction


class StockIndexItem(_Resource):
    ticker: Ticker
    name: str
    sector: str | None
    aliases: list[str] = Field(default_factory=list, description="Former names and tickers")
    status: Literal["active", "suspended", "delisted"]
    has_forecast: bool
    liquidity_rank: int | None = Field(
        default=None, ge=1, description="1 = most liquid; breaks search ties (24.3)"
    )
    last: LastPrice | None


class StocksIndex(_Resource):
    as_of_session: date
    items: list[StockIndexItem]

    @model_validator(mode="after")
    def _unique(self) -> StocksIndex:
        tickers = [item.ticker for item in self.items]
        if len(tickers) != len(set(tickers)):
            raise ValueError("tickers must be unique")
        return self


# ---------------------------------------------------------------------------- /v1/stocks/{ticker}
class LatestSession(_Resource):
    session: date
    close: PriceKes
    prev_close: PriceKes
    change: float
    change_pct: Fraction
    volume: int = Field(ge=0)
    turnover: Kes | None


class Range52w(_Resource):
    low: PriceKes
    high: PriceKes


class StockFlags(_Resource):
    suspended: bool
    corporate_action_today: bool
    ex_dividend_today: bool


class StockDetail(_Resource):
    ticker: Ticker
    name: str
    sector: str | None
    segment: str | None
    status: Literal["active", "suspended", "delisted"]
    latest: LatestSession | None
    range_52w: Range52w | None
    price_basis: Literal["vwap", "last", "unknown"] = Field(
        description="vwap: the official price is the volume-weighted average of the session"
    )
    flags: StockFlags


# ---------------------------------------------------------------------------- history
class PriceEvent(_Resource):
    date: date
    type: Literal["ex_dividend", "bonus", "split", "rights", "suspension", "listing", "large_move"]
    label: str


class PriceHistory(_Resource):
    """Columnar series to keep payloads small (22.3). Prices are as published."""

    ticker: Ticker
    range: Literal["1y", "max"]
    price_basis: Literal["vwap", "last", "unknown"]
    dates: list[date]
    close: list[PriceKes]
    volume: list[int | None]
    events: list[PriceEvent] = Field(default_factory=list)

    @model_validator(mode="after")
    def _shape(self) -> PriceHistory:
        _same_length(
            "history", dates=list(self.dates), close=list(self.close), volume=list(self.volume)
        )
        _ascending("history", self.dates)
        return self


# ---------------------------------------------------------------------------- prediction
class ForecastRange(_Resource):
    level: float = Field(default=0.8, ge=0.8, le=0.8, description="Always the 80% range in v1")
    lower: PriceKes
    upper: PriceKes


class ForecastLatest(_Resource):
    origin_session: date
    target_session: date
    last_close: PriceKes
    predicted_close: PriceKes
    predicted_return: Fraction = Field(description="May be rounded to 4 decimal places")
    range: ForecastRange
    model: ModelRef
    generated_at: Timestamp
    data_through: date
    is_late: bool
    target_in_past: bool = Field(
        description="True when the target session is before today on the user's machine"
    )
    target_from_calendar: bool = Field(
        description="False when the calendar does not cover the target: it is the next weekday"
    )

    @model_validator(mode="after")
    def _consistent(self) -> ForecastLatest:
        if not self.range.lower <= self.predicted_close <= self.range.upper:
            raise ValueError("expected range.lower <= predicted_close <= range.upper")
        if self.target_session <= self.origin_session:
            raise ValueError("target_session must come after origin_session")
        # Allow for rounding: the close to KES 0.01 and the return to 4 decimal places.
        implied = self.last_close * (1 + self.predicted_return)
        tolerance = 0.005 + 0.00005 * self.last_close + 1e-9
        if abs(implied - self.predicted_close) > tolerance:
            raise ValueError("predicted_close must equal last_close * (1 + predicted_return)")
        return self


class TrackRecord(_Resource):
    basis: Literal["live", "backtest"]
    window_sessions: int = Field(ge=1)
    n: int = Field(ge=0)
    mae_pct: ErrorSize
    naive_mae_pct: ErrorSize
    range_coverage: Share
    directional_accuracy: Share | None
    directional_n: int = Field(ge=0)


class PredictionHistoryRow(_Resource):
    origin_session: date
    target_session: date
    predicted_close: PriceKes
    lower: PriceKes
    upper: PriceKes
    actual_close: PriceKes | None
    error_pct: Fraction | None
    direction: DirectionOutcome | None
    in_range: bool | None
    model_id: str = Field(description="The model that made this forecast")


class StockPrediction(_Resource):
    ticker: Ticker
    latest: ForecastLatest | None
    unavailable_reason: UnavailableReason | None
    track_record: TrackRecord | None
    history: list[PredictionHistoryRow] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_of(self) -> StockPrediction:
        if (self.latest is None) == (self.unavailable_reason is None):
            raise ValueError("exactly one of latest and unavailable_reason must be set")
        return self


# ---------------------------------------------------------------------------- /v1/market/overview
class IndexSummary(_Resource):
    level: float = Field(gt=0)
    change_pct: Fraction


class MarketSummary(_Resource):
    nasi: IndexSummary | None
    nse20: IndexSummary | None
    advancers: int = Field(ge=0)
    decliners: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    turnover_kes: Kes
    turnover_vs_20d: float | None = Field(
        description="Total market turnover over its 20-session average; block trades included"
    )


class Mover(_Resource):
    ticker: Ticker
    name: str
    close: PriceKes
    change_pct: Fraction


class Movers(_Resource):
    min_turnover_kes: Kes
    gainers: list[Mover]
    losers: list[Mover]


class IndexTrend(_Resource):
    index: str
    dates: list[date]
    level: list[float]

    @model_validator(mode="after")
    def _shape(self) -> IndexTrend:
        _same_length("index_trend", dates=list(self.dates), level=list(self.level))
        _ascending("index_trend", self.dates)
        return self


class Breadth(_Resource):
    dates: list[date]
    advancers: list[int]
    decliners: list[int]
    unchanged: list[int]

    @model_validator(mode="after")
    def _shape(self) -> Breadth:
        _same_length(
            "breadth",
            dates=list(self.dates),
            advancers=list(self.advancers),
            decliners=list(self.decliners),
            unchanged=list(self.unchanged),
        )
        _ascending("breadth", self.dates)
        return self


class TrackRecordSeries(_Resource):
    """Rolling 60-session record of forecasts as published."""

    dates: list[date]
    model_mae_pct_60: list[ErrorSize]
    naive_mae_pct_60: list[ErrorSize]
    coverage_60: list[Share]
    basis: list[Literal["backtest", "live"]]
    model_label: list[str]

    @model_validator(mode="after")
    def _shape(self) -> TrackRecordSeries:
        _same_length(
            "track_record",
            dates=list(self.dates),
            model=list(self.model_mae_pct_60),
            naive=list(self.naive_mae_pct_60),
            coverage=list(self.coverage_60),
            basis=list(self.basis),
            model_label=list(self.model_label),
        )
        _ascending("track_record", self.dates)
        return self


class MarketCharts(_Resource):
    index_trend: IndexTrend
    breadth: Breadth
    track_record: TrackRecordSeries


class MarketOverview(_Resource):
    session: date
    summary: MarketSummary
    movers: Movers
    charts: MarketCharts


# ---------------------------------------------------------------------------- /report.json (v1.1)
class ReportPeriod(_Resource):
    start: date
    end: date


class ReportPeriods(_Resource):
    selection: ReportPeriod
    holdout: ReportPeriod


class ReportUniverse(_Resource):
    min: int = Field(ge=0)
    max: int = Field(ge=0)
    median: int = Field(ge=0)
    at_last_session: int = Field(ge=0)


class ReportGate(_Resource):
    id: str = Field(description="Gate id, e.g. G-SKILL (docs/methodology.md, Gates)")
    name: str = Field(description="Plain-language name shown in the app")
    passed: bool
    detail: str


class ReportScores(_Resource):
    mae: ErrorSize
    mae_no_change: ErrorSize
    skill: float = Field(description="1 - MAE / MAE of the no-change guess")
    dm_p: float | None = Field(description="One-sided Diebold-Mariano p-value against no change")
    coverage: Share | None = Field(description="Share of actual closes inside the 80% range")
    direction_accuracy: Share | None
    rows: int = Field(ge=0)
    securities: int = Field(ge=0)


class ReportModel(_Resource):
    model_id: str
    label: str
    is_champion: bool
    selection: ReportScores
    holdout: ReportScores | None
    gates: list[ReportGate]
    skill_by_year: dict[str, float]


class ReportChampion(_Resource):
    model_id: str
    label: str
    reason: str


class DataAudit(_Resource):
    sessions: int = Field(ge=0)
    securities: int = Field(ge=0)
    corrections_applied: int = Field(ge=0)
    rows_corrected: int = Field(ge=0)
    duplicates_dropped: int = Field(ge=0)
    missing_sessions: int = Field(ge=0)
    events_excluded: int = Field(ge=0)
    carried_forward_rows: int = Field(ge=0)


class Report(_Resource):
    """Evaluation results for the About page."""

    profile: Literal["default", "full"]
    refit: str
    periods: ReportPeriods
    dataset: DatasetInfo
    universe: ReportUniverse
    champion: ReportChampion
    headline: ReportScores | None = Field(description="The champion's holdout scores")
    models: list[ReportModel]
    data_audit: DataAudit


# ---------------------------------------------------------------------------- /site.json (v1.1)
class SiteLink(_Resource):
    label: str
    url: str = Field(pattern=r"^(https://|http://|mailto:)")


class Site(_Resource):
    """The builder's name and contact links from config/site.yaml, plus dataset attribution."""

    owner_name: str
    tagline: str
    links: list[SiteLink]
    attribution: str


# Published resources: file name in a release -> model. Schema files take the same names.
RESOURCES: dict[str, type[BaseModel]] = {
    "status": Status,
    "stocks": StocksIndex,
    "stock": StockDetail,
    "history": PriceHistory,
    "prediction": StockPrediction,
    "overview": MarketOverview,
    "report": Report,
    "site": Site,
}
