// Every user-visible sentence lives here, or in the About page's prose, so one test can enforce
// the language rules (ENGINEERING.md §15.3). Words such as "buy", "sell", "hold", "signal" and
// "target price" never appear.
import { formatSessionDate } from "./format";

export const COPY = {
  wordmark: "NSE Forecast",
  disclaimer: "Research forecast, not investment advice.",
  searchLabel: "Find an NSE stock",
  searchPlaceholder: "Search by ticker or company name",
  noMatches: (query: string) => `No NSE stock matches ‘${query}’. Try a ticker like SCOM.`,
  dataThrough: (session: string) => `Data through ${formatSessionDate(session)}`,
  withImports: "including sessions you imported",
  sampleData: "Sample data",
  mendeleyData: (version: number | null) => `Mendeley Data${version != null ? ` v${version}` : ""}`,
  localFiles: "Local files",
  staleBanner: (latest: string, next: string) =>
    `Market data is delayed. Showing the close of ${formatSessionDate(latest, false)}; the update for ${formatSessionDate(next, false)} has not arrived yet.`,
  cannotReach: "The results did not load. Check that the tool is still running, then retry.",
  retry: "Retry",
  sectionFailed: (section: string) => `${section} did not load.`,
  gainers: "Biggest gainers",
  losers: "Biggest losers",
  moversOn: (session: string) => `On ${formatSessionDate(session)}, the last session in the data.`,
  moversFilter: (minimum: string) => `Stocks that traded at least ${minimum} that day.`,
  indexTrend: "NASI over the past year",
  indexMoved: (index: string, from: string, start: string, to: string, end: string) =>
    `${index} moved from ${from} on ${formatSessionDate(start)} to ${to} on ${formatSessionDate(end)}.`,
  breadth: "Market breadth, last 60 sessions",
  breadthLatest: (up: number, down: number, flat: number) =>
    `Latest session: ${up} advancers, ${down} decliners, ${flat} unchanged.`,
  trackRecord: "How far off were the forecasts?",
  trackRecordHome: (model: string, naive: string, label: string) =>
    `Average miss over the last 60 sessions of the backtest: ${model} for the ${label}, against ${naive} for a no-change guess.`,
  trackRecordNoChange: (naive: string) =>
    `No model passed the gates, so the forecasts are the no-change guess itself. Over the last 60 sessions of the backtest it missed by ${naive} of price on average.`,
  forecastFor: (target: string) => `Model forecast for ${formatSessionDate(target)}`,
  nextWeekday: "next weekday (calendar not available)",
  targetInPast: (last: string) =>
    `The dataset ends on ${formatSessionDate(last)}, so this is the forecast the model would have made that evening.`,
  forecastClose: "Forecast close",
  expectedRange: "80% expected range",
  backtestLabel: (period: string) => `Simulated (backtest), ${period}`,
  trackRecordSentence: (n: number, model: string, naive: string, coverage: string) =>
    `Over ${n.toLocaleString("en-KE")} forecasts this model missed by ${model} of price on average; a no-change guess missed by ${naive}. The actual close fell inside the range ${coverage} of the time.`,
  generated: (model: string, version: string, when: string, through: string) =>
    `${model} (run ${version}). Generated ${when}, using data up to the ${formatSessionDate(through, false)} close.`,
  lateForecast: "This forecast was published after the market opened.",
  noForecast: {
    NOT_IN_FORECAST_UNIVERSE:
      "No forecast for this stock. Forecasts cover ordinary shares that traded on at least 80% of the last 250 sessions, with enough daily turnover and at least two years of history.",
    INSUFFICIENT_HISTORY: "No forecast: this stock does not have enough recent, gap-free trading history.",
    SUSPENDED: "Trading in this stock is suspended, so there is no forecast.",
    DATA_QUALITY_HOLD: "Forecasts are paused while the data is checked.",
    PIPELINE_DELAYED: "The forecast is not ready yet.",
    MODEL_UNAVAILABLE: "The forecasting model is unavailable, so there is no forecast.",
    RECENT_PRICE_EVENT:
      "No forecast: the price moved beyond the ±10% daily band in the last 60 sessions, so its recent prices are left out of modelling.",
  },
  historyTitle: "Backtest forecasts versus actual closes",
  direction: { hit: "Correct", miss: "Wrong", no_change: "No change" },
  unknownTicker: (ticker: string) => `There is no NSE stock with ticker ${ticker}.`,
  noLongerQuoted: (session: string) =>
    `The data has no prices for this security after ${formatSessionDate(session)}: it has left the market or changed its ticker.`,
  closeOn: (session: string) => `Close on ${formatSessionDate(session)}`,
  officialPrice: "Official closing price: the volume-weighted average price of the session.",
  dataGap: (from: string, to: string) =>
    `The dataset has no prices between ${formatSessionDate(from)} and ${formatSessionDate(to)}, so the line is broken there.`,
  largeMoves: (count: number) =>
    `${count} ${count === 1 ? "move" : "moves"} beyond the ±10% daily band in this period (marked on the chart) ${count === 1 ? "is" : "are"} left out of modelling.`,
  pageNotFound: "This page does not exist.",
  dataCredit: "Data:",
  dataOrigin: "Daily prices from the Nairobi Securities Exchange, as compiled in the dataset cited above.",
  builtBy: (owner: string) => `Built by ${owner}`,
  contactInvite: "Questions, ideas and collaboration are welcome.",
  sampleNotice: "Showing synthetic sample data. Run without --sample to use real NSE data.",
} as const;
