import { describe, expect, it } from "vitest";
import type { StockIndexItem } from "../api";
import { normalise, resolveAlias, search } from "./search";

const item = (ticker: string, name: string, rank: number, aliases: string[] = []): StockIndexItem => ({
  ticker,
  name,
  sector: null,
  aliases,
  status: "active",
  has_forecast: true,
  liquidity_rank: rank,
  last: null,
});

const ITEMS = [
  item("SCOM", "Safaricom PLC", 1),
  item("SCBK", "Standard Chartered Bank Kenya", 9),
  item("ABSA", "Absa Bank Kenya PLC", 5, ["Barclays Bank of Kenya"]),
  item("NCBA", "NCBA Group PLC", 6, ["NIC Group", "Commercial Bank of Africa"]),
  item("KCB", "KCB Group Plc", 3),
  item("CTUM", "Centum Investment Company Plc", 20),
];

describe("search", () => {
  it("normalises case, accents, ampersands and punctuation", () => {
    expect(normalise("  Café & Co.  ")).toBe("cafe and co");
  });

  it("ranks exact ticker, ticker prefix, name prefix, word prefix, alias, substring", () => {
    expect(search(ITEMS, "kcb").map((i) => i.ticker)[0]).toBe("KCB");
    expect(search(ITEMS, "sc").map((i) => i.ticker)).toEqual(["SCOM", "SCBK"]);
    expect(search(ITEMS, "safari").map((i) => i.ticker)).toEqual(["SCOM"]);
    expect(search(ITEMS, "group").map((i) => i.ticker)).toEqual(["KCB", "NCBA"]);
    expect(search(ITEMS, "barclays").map((i) => i.ticker)).toEqual(["ABSA"]);
    expect(search(ITEMS, "vestment").map((i) => i.ticker)).toEqual(["CTUM"]);
  });

  it("breaks ties by liquidity, then alphabetically", () => {
    expect(search(ITEMS, "bank").map((i) => i.ticker)).toEqual(["ABSA", "SCBK", "NCBA"]);
  });

  it("returns at most eight results and nothing for blank queries", () => {
    const many = Array.from({ length: 12 }, (_, i) => item(`T${i}X`, `Test ${i}`, i + 1));
    expect(search(many, "test")).toHaveLength(8);
    expect(search(ITEMS, "   ")).toEqual([]);
  });

  it("resolves a former name to the current security", () => {
    expect(resolveAlias(ITEMS, "Barclays Bank of Kenya")?.ticker).toBe("ABSA");
    expect(resolveAlias(ITEMS, "XYZ")).toBeUndefined();
  });
});
