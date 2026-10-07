import type { Status } from "./index";

// The API root: fixtures in development, the CDN-backed bucket in production (ADR-012).
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api/v1";

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

// status.json names the current immutable release; everything else is read relative to it,
// so one page never mixes data from two releases (ENGINEERING.md 22.2).
export function releasePath(status: Pick<Status, "release_id">, path: string): string {
  return `r/${status.release_id}/${path}`;
}
