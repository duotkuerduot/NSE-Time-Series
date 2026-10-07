import type { Status } from "../api";

// A static system reports its own staleness: if the next release has not replaced status.json
// by `stale_after`, the frontend shows the banner without any server involved (22.3).
export function isStale(status: Pick<Status, "stale_after">, now: Date = new Date()): boolean {
  return now.getTime() > new Date(status.stale_after).getTime();
}
