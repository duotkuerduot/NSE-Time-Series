// Every user-visible sentence lives here so one test can enforce the language rules
// (ENGINEERING.md 24.7). Words such as "buy", "sell", "signal" and "target price" never appear.
import { formatSessionDate } from "./format";

export const COPY = {
  wordmark: "NSE Forecast",
  disclaimer: "Research forecast, not investment advice.",
  searchLabel: "Find an NSE stock",
  searchPlaceholder: "Search by ticker or company name",
  noMatches: (query: string) => `No NSE stock matches ‘${query}’. Try a ticker like SCOM.`,
  dataTo: (session: string) => `Market data to ${formatSessionDate(session)}`,
  updated: (when: string) => `Updated ${when}`,
  staleBanner: (latest: string, next: string) =>
    `Market data is delayed. Showing the close of ${formatSessionDate(latest, false)}; the update for ${formatSessionDate(next, false)} has not arrived yet.`,
  cannotReach: "We cannot reach the market data right now.",
  retry: "Retry",
  sectionFailed: (section: string) => `${section} did not load.`,
  gainers: "Biggest gainers",
  losers: "Biggest losers",
  moversFilter: (minimum: string) => `Traded with turnover of at least ${minimum}`,
  indexTrend: "NASI over the past year",
  breadth: "Market breadth, last 60 sessions",
  trackRecord: "How far off were the forecasts?",
  chartsLater: "Interactive charts arrive in Phase 10; the figures below come from the same data.",
  forecastFor: (target: string) => `Model forecast for ${formatSessionDate(target)}`,
  forecastClose: "Forecast close",
  expectedRange: "80% expected range",
  trackRecordSentence: (model: string, naive: string, coverage: string, basis: "live" | "backtest") =>
    `${basis === "live" ? "Over the last 60 sessions" : "In simulated (backtest) testing over 60 sessions"} this model missed by ${model} of price on average; a no-change guess missed by ${naive}. The actual close fell inside the range in ${coverage} of sessions.`,
  generated: (model: string, version: string, when: string, through: string) =>
    `${model}, version ${version}. Generated ${when}, using data up to the ${formatSessionDate(through, false)} close.`,
  lateForecast: "This forecast was published after the market opened.",
  noForecast: {
    NOT_IN_FORECAST_UNIVERSE: "No forecast for this stock. It trades too rarely for a reliable model.",
    INSUFFICIENT_HISTORY: "No forecast yet: this stock does not have enough trading history.",
    SUSPENDED: "Trading in this stock is suspended, so there is no forecast.",
    DATA_QUALITY_HOLD: "Today's forecast is paused while we check the latest market data.",
    PIPELINE_DELAYED: "Today's forecast is delayed. The latest update has not arrived yet.",
    MODEL_UNAVAILABLE: "The forecasting model is unavailable today, so there is no forecast.",
  },
  historyTitle: "Forecasts versus actual closes",
  direction: { hit: "Correct", miss: "Wrong", no_change: "No change" },
  unknownTicker: (ticker: string) => `There is no NSE stock with ticker ${ticker}.`,
  closeOn: (session: string) => `Close on ${formatSessionDate(session)}`,
  officialPrice: "Official closing price: the volume-weighted average of the session.",
  pageNotFound: "This page does not exist.",
  attribution:
    "Market data: Nairobi Securities Exchange, end of day. © Nairobi Securities Exchange. The NSE is not responsible for errors or omissions.",
} as const;
