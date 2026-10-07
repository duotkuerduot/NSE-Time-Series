// Generated from contracts/api/v1 by `pnpm gen:types`. Do not edit.


/**
 * NSE ticker, e.g. SCOM
 */
export type Ticker = string
export type OriginSession = string
export type TargetSession = string
/**
 * Price in Kenya shillings
 */
export type LastClose = number
/**
 * Price in Kenya shillings
 */
export type PredictedClose = number
/**
 * May be rounded to 4 decimal places
 */
export type PredictedReturn = number
/**
 * Always the 80% range in v1
 */
export type Level = number
/**
 * Price in Kenya shillings
 */
export type Lower = number
/**
 * Price in Kenya shillings
 */
export type Upper = number
export type ModelId = string
/**
 * Display name, e.g. 'LightGBM' or 'No-change baseline'
 */
export type Label = string
export type Version = string
/**
 * ISO 8601 with offset, e.g. ...Z
 */
export type GeneratedAt = string
export type DataThrough = string
export type IsLate = boolean
/**
 * Why a security has no forecast in a release (ENGINEERING.md 22.3).
 */
export type UnavailableReason = ("NOT_IN_FORECAST_UNIVERSE" | "INSUFFICIENT_HISTORY" | "SUSPENDED" | "DATA_QUALITY_HOLD" | "PIPELINE_DELAYED" | "MODEL_UNAVAILABLE")
export type Basis = ("live" | "backtest")
export type WindowSessions = number
export type N = number
/**
 * An average absolute error, e.g. 0.0124
 */
export type MaePct = number
/**
 * An average absolute error, e.g. 0.0124
 */
export type NaiveMaePct = number
/**
 * A share of cases, e.g. 0.8 for 80%
 */
export type RangeCoverage = number
export type DirectionalAccuracy = (number | null)
export type DirectionalN = number
export type OriginSession1 = string
export type TargetSession1 = string
/**
 * Price in Kenya shillings
 */
export type PredictedClose1 = number
/**
 * Price in Kenya shillings
 */
export type Lower1 = number
/**
 * Price in Kenya shillings
 */
export type Upper1 = number
export type ActualClose = (number | null)
export type ErrorPct = (number | null)
export type DirectionOutcome = ("hit" | "miss" | "no_change")
export type InRange = (boolean | null)
/**
 * The model that made this forecast (review FE-4)
 */
export type ModelId1 = string
export type History = PredictionHistoryRow[]

export interface StockPrediction {
ticker: Ticker
latest: (ForecastLatest | null)
unavailable_reason: (UnavailableReason | null)
track_record: (TrackRecord | null)
history: History
}
export interface ForecastLatest {
origin_session: OriginSession
target_session: TargetSession
last_close: LastClose
predicted_close: PredictedClose
predicted_return: PredictedReturn
range: ForecastRange
model: ModelRef
generated_at: GeneratedAt
data_through: DataThrough
is_late: IsLate
}
export interface ForecastRange {
level: Level
lower: Lower
upper: Upper
}
export interface ModelRef {
model_id: ModelId
label: Label
version: Version
}
export interface TrackRecord {
basis: Basis
window_sessions: WindowSessions
n: N
mae_pct: MaePct
naive_mae_pct: NaiveMaePct
range_coverage: RangeCoverage
directional_accuracy: DirectionalAccuracy
directional_n: DirectionalN
}
export interface PredictionHistoryRow {
origin_session: OriginSession1
target_session: TargetSession1
predicted_close: PredictedClose1
lower: Lower1
upper: Upper1
actual_close: ActualClose
error_pct: ErrorPct
direction: (DirectionOutcome | null)
in_range: InRange
model_id: ModelId1
}
