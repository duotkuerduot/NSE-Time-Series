import { describe, expect, it } from "vitest";
import { isStale } from "./staleness";

describe("staleness", () => {
  const status = { stale_after: "2026-10-08T19:00:00Z" };

  it("is fresh before the deadline and stale after it", () => {
    expect(isStale(status, new Date("2026-10-08T18:59:59Z"))).toBe(false);
    expect(isStale(status, new Date("2026-10-08T19:00:01Z"))).toBe(true);
  });
});
