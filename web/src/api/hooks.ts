import { useQuery } from "@tanstack/react-query";
import { fetchJson, NotFoundError, releasePath } from "./client";
import type {
  MarketOverview,
  PriceHistory,
  Status,
  StockDetail,
  StockPrediction,
  StocksIndex,
} from "./index";

const retry = (count: number, error: unknown) => !(error instanceof NotFoundError) && count < 2;

export function useStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: () => fetchJson<Status>("status.json"),
    staleTime: 60_000,
    retry,
  });
}

function useReleaseResource<T>(path: string | null) {
  const status = useStatus();
  const release = status.data?.release_id;
  return useQuery({
    queryKey: ["release", release, path],
    queryFn: () => fetchJson<T>(releasePath({ release_id: release as string }, path as string)),
    enabled: Boolean(release && path),
    staleTime: Infinity, // releases are immutable
    retry,
  });
}

export const useStocks = () => useReleaseResource<StocksIndex>("stocks.json");
export const useOverview = () => useReleaseResource<MarketOverview>("market/overview.json");
export const useStock = (ticker: string) => useReleaseResource<StockDetail>(`stocks/${ticker}.json`);
export const useHistory = (ticker: string, range: "1y" | "max") =>
  useReleaseResource<PriceHistory>(`stocks/${ticker}/history.${range}.json`);
export const usePrediction = (ticker: string) =>
  useReleaseResource<StockPrediction>(`stocks/${ticker}/prediction.json`);
