// Generated from contracts/api/v1 by `pnpm gen:types`. Do not edit.


/**
 * NSE ticker, e.g. SCOM
 */
export type Ticker = string
export type Name = string
export type Sector = (string | null)
export type Segment = (string | null)
export type Status = ("active" | "suspended" | "delisted")
export type Session = string
/**
 * Price in Kenya shillings
 */
export type Close = number
/**
 * Price in Kenya shillings
 */
export type PrevClose = number
export type Change = number
/**
 * A ratio, e.g. 0.0124 for 1.24%
 */
export type ChangePct = number
export type Volume = number
export type Turnover = (number | null)
/**
 * Price in Kenya shillings
 */
export type Low = number
/**
 * Price in Kenya shillings
 */
export type High = number
/**
 * vwap: the official price is the volume-weighted average of the session
 */
export type PriceBasis = ("vwap" | "last" | "unknown")
export type Suspended = boolean
export type CorporateActionToday = boolean
export type ExDividendToday = boolean

export interface StockDetail {
ticker: Ticker
name: Name
sector: Sector
segment: Segment
status: Status
latest: (LatestSession | null)
range_52w: (Range52W | null)
price_basis: PriceBasis
flags: StockFlags
}
export interface LatestSession {
session: Session
close: Close
prev_close: PrevClose
change: Change
change_pct: ChangePct
volume: Volume
turnover: Turnover
}
export interface Range52W {
low: Low
high: High
}
export interface StockFlags {
suspended: Suspended
corporate_action_today: CorporateActionToday
ex_dividend_today: ExDividendToday
}
