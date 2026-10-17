import { describe, expect, it } from "vitest";
import {
  forecastChangeText,
  formatChange,
  formatCompactKes,
  formatEat,
  formatKes,
  formatPct,
  formatSessionDate,
  formatSignedPrice,
  gapStarts,
} from "./format";

describe("format", () => {
  it("formats money with two decimals", () => {
    expect(formatKes(28.45)).toBe("KES 28.45");
    expect(formatKes(1234.5)).toBe("KES 1,234.50");
    expect(formatCompactKes(612_400_000)).toBe("KES 612m");
    expect(formatCompactKes(100_000)).toBe("KES 100k");
  });

  it("signs percentages with a true minus", () => {
    expect(formatPct(0.0124)).toBe("+1.24%");
    expect(formatPct(-0.0073)).toBe("−0.73%");
    expect(formatPct(0)).toBe("0.00%");
    expect(formatPct(-0.00001)).toBe("0.00%");
  });

  it("never relies on colour alone", () => {
    expect(formatChange(0.0124)).toEqual({ text: "▲ +1.24%", direction: "up" });
    expect(formatChange(-0.0073).direction).toBe("down");
    expect(formatChange(0).direction).toBe("flat");
  });

  it("says no change inside the ±0.1% band", () => {
    expect(forecastChangeText(0.0005)).toBe("≈ no change expected");
    expect(forecastChangeText(0.0056)).toBe("+0.56% from last close");
  });

  it("formats session dates without time-zone drift", () => {
    expect(formatSessionDate("2026-10-07")).toBe("Wed 7 Oct 2026");
    expect(formatSessionDate("2026-10-21", false)).toBe("Wed 21 Oct");
    expect(formatSessionDate("2026-09-25")).toBe("Fri 25 Sep 2026");
  });

  it("signs absolute price changes", () => {
    expect(formatSignedPrice(0.87)).toBe("+0.87");
    expect(formatSignedPrice(-0.35)).toBe("\u22120.35");
    expect(formatSignedPrice(0)).toBe("0.00");
  });

  it("shows timestamps in Nairobi time", () => {
    expect(formatEat("2026-10-07T15:47:55Z")).toBe("7 Oct 2026, 18:47 EAT");
  });
});

describe("periods and shares", () => {
  it("formats months, periods and unsigned shares", async () => {
    const { formatMonthYear, formatPeriod, formatShare } = await import("./format");
    expect(formatMonthYear("2023-01-03")).toBe("Jan 2023");
    expect(formatPeriod("2023-01-01", "2025-10-30")).toBe("Jan 2023 to Oct 2025");
    expect(formatShare(0.8012)).toBe("80.1%");
    expect(formatShare(0.0142, 2)).toBe("1.42%");
  });

  it("finds holes in the data but not weekends or holiday runs", () => {
    expect(gapStarts(["2024-12-24", "2024-12-27", "2024-12-30"])).toEqual([]); // Christmas
    expect(gapStarts(["2026-04-02", "2026-04-07"])).toEqual([]); // Easter: Thu -> Tue
    // November and December 2025 are missing from the dataset.
    expect(gapStarts(["2025-10-30", "2025-10-31", "2026-01-02", "2026-01-05"])).toEqual([2]);
    expect(gapStarts([])).toEqual([]);
  });
});
