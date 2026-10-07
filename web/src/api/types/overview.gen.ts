// Generated from contracts/api/v1 by `pnpm gen:types`. Do not edit.


export type Session = string
export type Level = number
/**
 * A ratio, e.g. 0.0124 for 1.24%
 */
export type ChangePct = number
export type Advancers = number
export type Decliners = number
export type Unchanged = number
/**
 * Kenya shillings
 */
export type TurnoverKes = number
/**
 * Total market turnover over its 20-session average; block trades included
 */
export type TurnoverVs20D = (number | null)
/**
 * Kenya shillings
 */
export type MinTurnoverKes = number
/**
 * NSE ticker, e.g. SCOM
 */
export type Ticker = string
export type Name = string
/**
 * Price in Kenya shillings
 */
export type Close = number
/**
 * A ratio, e.g. 0.0124 for 1.24%
 */
export type ChangePct1 = number
export type Gainers = Mover[]
export type Losers = Mover[]
export type Index = string
export type Dates = string[]
export type Level1 = number[]
export type Dates1 = string[]
export type Advancers1 = number[]
export type Decliners1 = number[]
export type Unchanged1 = number[]
export type Dates2 = string[]
/**
 * Items: An average absolute error, e.g. 0.0124
 */
export type ModelMaePct60 = number[]
/**
 * Items: An average absolute error, e.g. 0.0124
 */
export type NaiveMaePct60 = number[]
/**
 * Items: A share of cases, e.g. 0.8 for 80%
 */
export type Coverage60 = number[]
export type Basis = ("backtest" | "live")[]
export type ModelLabel = string[]

export interface MarketOverview {
session: Session
summary: MarketSummary
movers: Movers
charts: MarketCharts
}
export interface MarketSummary {
nasi: (IndexSummary | null)
nse20: (IndexSummary | null)
advancers: Advancers
decliners: Decliners
unchanged: Unchanged
turnover_kes: TurnoverKes
turnover_vs_20d: TurnoverVs20D
}
export interface IndexSummary {
level: Level
change_pct: ChangePct
}
export interface Movers {
min_turnover_kes: MinTurnoverKes
gainers: Gainers
losers: Losers
}
export interface Mover {
ticker: Ticker
name: Name
close: Close
change_pct: ChangePct1
}
export interface MarketCharts {
index_trend: IndexTrend
breadth: Breadth
track_record: TrackRecordSeries
}
export interface IndexTrend {
index: Index
dates: Dates
level: Level1
}
export interface Breadth {
dates: Dates1
advancers: Advancers1
decliners: Decliners1
unchanged: Unchanged1
}
/**
 * Rolling 60-session record of forecasts as published (review FE-4).
 */
export interface TrackRecordSeries {
dates: Dates2
model_mae_pct_60: ModelMaePct60
naive_mae_pct_60: NaiveMaePct60
coverage_60: Coverage60
basis: Basis
model_label: ModelLabel
}
