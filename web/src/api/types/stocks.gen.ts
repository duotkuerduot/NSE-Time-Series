// Generated from contracts/api/v1 by `pnpm gen:types`. Do not edit.


export type AsOfSession = string
/**
 * NSE ticker, e.g. SCOM
 */
export type Ticker = string
export type Name = string
export type Sector = (string | null)
/**
 * Former names and tickers
 */
export type Aliases = string[]
export type Status = ("active" | "suspended" | "delisted")
export type HasForecast = boolean
/**
 * 1 = most liquid; breaks search ties (24.3)
 */
export type LiquidityRank = (number | null)
/**
 * Price in Kenya shillings
 */
export type Close = number
/**
 * A ratio, e.g. 0.0124 for 1.24%
 */
export type ChangePct = number
export type Items = StockIndexItem[]

export interface StocksIndex {
as_of_session: AsOfSession
items: Items
}
export interface StockIndexItem {
ticker: Ticker
name: Name
sector: Sector
aliases: Aliases
status: Status
has_forecast: HasForecast
liquidity_rank: LiquidityRank
last: (LastPrice | null)
}
export interface LastPrice {
close: Close
change_pct: ChangePct
}
