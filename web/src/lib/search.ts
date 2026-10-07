import type { StockIndexItem } from "../api";

// Client-side search over the securities index (ENGINEERING.md 22.3, 24.3).
export const MAX_RESULTS = 8;

export function normalise(text: string): string {
  return text
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9 ]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

// Lower is better: exact ticker, ticker prefix, name prefix, word prefix, alias, substring.
export function score(item: StockIndexItem, query: string): number | null {
  const q = normalise(query);
  if (!q) return null;
  const ticker = normalise(item.ticker);
  const name = normalise(item.name);
  if (ticker === q) return 0;
  if (ticker.startsWith(q)) return 1;
  if (name.startsWith(q)) return 2;
  if (name.split(" ").some((word) => word.startsWith(q))) return 3;
  if ((item.aliases ?? []).some((alias) => normalise(alias).includes(q))) return 4;
  if (name.includes(q)) return 5;
  return null;
}

export function search(items: StockIndexItem[], query: string, limit = MAX_RESULTS): StockIndexItem[] {
  return items
    .map((item) => ({ item, rank: score(item, query) }))
    .filter((entry): entry is { item: StockIndexItem; rank: number } => entry.rank !== null)
    .sort(
      (a, b) =>
        a.rank - b.rank ||
        (a.item.liquidity_rank ?? Number.MAX_SAFE_INTEGER) -
          (b.item.liquidity_rank ?? Number.MAX_SAFE_INTEGER) ||
        a.item.ticker.localeCompare(b.item.ticker),
    )
    .slice(0, limit)
    .map((entry) => entry.item);
}

/** A former ticker or name resolves to the current security (22.3). */
export function resolveAlias(items: StockIndexItem[], ticker: string): StockIndexItem | undefined {
  const q = normalise(ticker);
  return items.find((item) => (item.aliases ?? []).some((alias) => normalise(alias) === q));
}
