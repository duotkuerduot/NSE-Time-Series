// Generated from contracts/api/v1 by `pnpm gen:types`. Do not edit.


/**
 * NSE ticker, e.g. SCOM
 */
export type Ticker = string
export type Range = ("1y" | "max")
export type PriceBasis = ("vwap" | "last" | "unknown")
export type Dates = string[]
/**
 * Items: Price in Kenya shillings
 */
export type Close = number[]
export type Volume = (number | null)[]
export type Date = string
export type Type = ("ex_dividend" | "bonus" | "split" | "rights" | "suspension" | "listing")
export type Label = string
export type Events = PriceEvent[]

/**
 * Columnar series to keep payloads small (22.3). Prices are as published.
 */
export interface PriceHistory {
ticker: Ticker
range: Range
price_basis: PriceBasis
dates: Dates
close: Close
volume: Volume
events: Events
}
export interface PriceEvent {
date: Date
type: Type
label: Label
}
