import type { Status } from "../api";

// The banner shows only when a release declares when the next one is due and that time has
// passed. Local runs publish `stale_after: null`: historical data is never late.
export function isStale(status: Pick<Status, "stale_after">, now: Date = new Date()): boolean {
  if (status.stale_after == null) return false;
  return now.getTime() > new Date(status.stale_after).getTime();
}
