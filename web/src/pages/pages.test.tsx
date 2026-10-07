// Phase 0 acceptance: every page renders from the contract fixtures (ENGINEERING.md 34).
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

const FIXTURES = resolve(__dirname, "../../../contracts/api/v1/fixtures");

function fixtureFetch(input: RequestInfo | URL): Promise<Response> {
  const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
  const path = url.replace(/^.*\/api\/v1\//, "");
  try {
    const body = readFileSync(resolve(FIXTURES, path), "utf8");
    return Promise.resolve(new Response(body, { status: 200, headers: { "Content-Type": "application/json" } }));
  } catch {
    return Promise.resolve(new Response("{}", { status: 404 }));
  }
}

function renderAt(path: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("pages render from fixtures", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(fixtureFetch));
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-07T16:00:00Z")); // before stale_after
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("home: summary, movers and the three context sections", async () => {
    renderAt("/");
    expect(screen.getByRole("heading", { level: 1, name: "Find an NSE stock" })).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "Find an NSE stock" })).toBeTruthy();
    expect(await screen.findByText("Biggest gainers")).toBeTruthy();
    expect(await screen.findByText(/NASI moved from/)).toBeTruthy();
    expect(await screen.findByText(/60-session average miss/)).toBeTruthy();
    expect(screen.getByText(/Fixture data: values are illustrative/)).toBeTruthy();
    expect(screen.queryByText(/Market data is delayed/)).toBeNull();
  });

  it("stock with a forecast: header, forecast panel and history", async () => {
    renderAt("/stocks/SCOM");
    expect(await screen.findByRole("heading", { name: "Safaricom PLC" })).toBeTruthy();
    expect(await screen.findByText(/Model forecast for Thu 8 Oct 2026/)).toBeTruthy();
    expect(await screen.findByText(/80% expected range/)).toBeTruthy();
    expect(await screen.findByText("Forecasts versus actual closes")).toBeTruthy();
    expect(screen.getAllByText("Research forecast, not investment advice.").length).toBeGreaterThan(0);
  });

  it("stock outside the forecast universe explains why", async () => {
    renderAt("/stocks/KUKZ");
    expect(await screen.findByText(/trades too rarely for a reliable model/)).toBeTruthy();
  });

  it("suspended stock", async () => {
    renderAt("/stocks/UCHM");
    expect(await screen.findByText(/Trading in this stock is suspended/)).toBeTruthy();
  });

  it("unknown ticker", async () => {
    renderAt("/stocks/ZZZZ");
    expect(await screen.findByText("There is no NSE stock with ticker ZZZZ.")).toBeTruthy();
  });

  it("about and not-found pages", async () => {
    renderAt("/about");
    expect(await screen.findByRole("heading", { name: "How the forecasts work" })).toBeTruthy();
    renderAt("/no-such-page");
    expect(await screen.findByText("This page does not exist.")).toBeTruthy();
  });

  it("shows the stale banner once stale_after has passed", async () => {
    vi.setSystemTime(new Date("2026-10-08T19:30:00Z"));
    renderAt("/");
    expect(await screen.findByText(/Market data is delayed/)).toBeTruthy();
  });
});
