import type { Status } from "./index";

// The API is the static JSON that `nsefc publish` writes to data/api/v1 and `nsefc serve`
// serves next to the app. In development, Vite serves the contract
// fixtures at the same path.
export const API_BASE = "/api/v1";

export class NotFoundError extends Error {
  constructor(public readonly path: string) {
    super(`Not found: ${path}`);
    this.name = "NotFoundError";
  }
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}/${path}`, { ...init, headers: { Accept: "application/json" } });
  if (response.status === 404) throw new NotFoundError(path);
  if (!response.ok) throw new Error(`Request for ${path} failed with ${response.status}`);
  return (await response.json()) as T;
}

// status.json names the current release; everything else is read from that release's folder,
// so one page never mixes data from two runs.
export function releasePath(status: Pick<Status, "release_id">, path: string): string {
  return `r/${status.release_id}/${path}`;
}
