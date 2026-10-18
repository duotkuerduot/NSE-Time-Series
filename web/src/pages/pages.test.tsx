// Every page renders from the contract fixtures (contracts/api/v1/fixtures), plus what the
// local tool adds: the data-through label, no stale banner when stale_after is null, the
// target_in_past line, the Results section, contact links, and the sample notice.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";

const FIXTURES = resolve(__dirname, "../../../contracts/api/v1/fixtures");
type Json = Record<string, unknown>;
type Patch = (body: Json) => Json;

function stubFetch(patches: Record<string, Patch> = {}) {
  const fetchFixture = (input: RequestInfo | URL): Promise<Response> => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.pathname : input.url;
    const path = url.replace(/^.*\/api\/v1\//, "");
    try {
      let body = JSON.parse(readFileSync(resolve(FIXTURES, path), "utf8")) as Json;
      const patch = Object.entries(patches).find(([suffix]) => path.endsWith(suffix))?.[1];
      if (patch) body = patch(body);
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
    } catch {
      return Promise.resolve(new Response("{}", { status: 404 }));
    }
  };
  vi.stubGlobal("fetch", vi.fn(fetchFixture));
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
    stubFetch();
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-16T19:30:00Z"));
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("home: data-through label, movers, charts and the track record", async () => {
    renderAt("/");
    expect(screen.getByRole("heading", { level: 1, name: "Find an NSE stock" })).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "Find an NSE stock" })).toBeTruthy();
    expect(await screen.findByText("Data through Fri 31 Oct 2025 · Mendeley Data v1")).toBeTruthy();
    expect(await screen.findByText("Biggest gainers")).toBeTruthy();
    expect(await screen.findByText(/NASI moved from/)).toBeTruthy();
    expect(await screen.findByText(/Average miss over the last 60 sessions of the backtest/)).toBeTruthy();
    expect(screen.getByRole("img", { name: "NASI level over the past year" })).toBeTruthy();
    expect(screen.getByText(/Fixture data: values are illustrative/)).toBeTruthy();
  });

  it("never shows the stale banner when stale_after is null", async () => {
    vi.setSystemTime(new Date("2030-01-01T00:00:00Z"));
    renderAt("/");
    await screen.findByText("Biggest gainers");
    expect(screen.queryByText(/Market data is delayed/)).toBeNull();
  });

  it("shows the stale banner once a non-null stale_after has passed", async () => {
    stubFetch({ "status.json": (body) => ({ ...body, stale_after: "2025-11-03T16:00:00Z" }) });
    renderAt("/");
    expect(await screen.findByText(/Market data is delayed/)).toBeTruthy();
  });

  it("stock with a forecast: target in the past, backtest label, range and history", async () => {
    renderAt("/stocks/SCOM");
    expect(await screen.findByRole("heading", { name: "Safaricom PLC" })).toBeTruthy();
    expect(await screen.findByText(/Model forecast for Mon 3 Nov 2025/)).toBeTruthy();
    expect(
      await screen.findByText(
        "The dataset ends on Fri 31 Oct 2025, so this is the forecast the model would have made that evening.",
      ),
    ).toBeTruthy();
    expect(await screen.findByText(/80% expected range/)).toBeTruthy();
    expect((await screen.findAllByText(/Simulated \(backtest\), Jan 2023 to Oct 2025/)).length).toBeGreaterThan(0);
    expect(await screen.findByText("Backtest forecasts versus actual closes")).toBeTruthy();
    expect(screen.getAllByText("Research forecast, not investment advice.").length).toBeGreaterThan(0);
    expect(screen.queryByText(/calendar not available/)).toBeNull();
  });

  it("breaks the price line across a hole in the data and says so", async () => {
    stubFetch({
      "SCOM/history.1y.json": (body) => ({
        ...body,
        dates: ["2025-10-30", "2025-10-31", "2026-01-02", "2026-01-05"],
        close: [29.55, 30.25, 28.5, 29.0],
        volume: [100, 200, 300, 400],
        events: [],
      }),
    });
    const { container } = renderAt("/stocks/SCOM");
    expect(
      await screen.findByText(
        "The dataset has no prices between Fri 31 Oct 2025 and Fri 2 Jan 2026, so the line is broken there.",
      ),
    ).toBeTruthy();
    const line = container.querySelector("path.line.ink")?.getAttribute("d") ?? "";
    expect(line.match(/M/g)?.length).toBe(2);
  });

  it("labels a target date that is not from the calendar", async () => {
    stubFetch({
      "SCOM/prediction.json": (body) => ({
        ...body,
        latest: { ...(body.latest as Json), target_from_calendar: false, target_in_past: false },
      }),
    });
    renderAt("/stocks/SCOM");
    expect(await screen.findByText(/next weekday \(calendar not available\)/)).toBeTruthy();
    expect(screen.queryByText(/so this is the forecast the model would have made/)).toBeNull();
  });

  it("stock outside the forecast universe explains why", async () => {
    renderAt("/stocks/KUKZ");
    expect(await screen.findByText(/Forecasts cover ordinary shares that traded on at least 80%/)).toBeTruthy();
    expect(screen.queryByText(/has left the market/)).toBeNull();
  });

  it("suspended stock", async () => {
    renderAt("/stocks/UCHM");
    expect(await screen.findByText(/Trading in this stock is suspended/)).toBeTruthy();
  });

  it("unknown ticker", async () => {
    renderAt("/stocks/ZZZZ");
    expect(await screen.findByText("There is no NSE stock with ticker ZZZZ.")).toBeTruthy();
  });

  it("about: results, gate table, skill by year, attribution and contact links", async () => {
    renderAt("/about");
    expect(await screen.findByRole("heading", { name: "How the forecasts work" })).toBeTruthy();
    expect(await screen.findByText(/the champion,/)).toBeTruthy();
    expect(await screen.findByText("Every model, through the same gates")).toBeTruthy();
    expect(await screen.findByText("Skill by year: LightGBM")).toBeTruthy();
    expect(screen.getByRole("img", { name: /skill against the no-change guess, by year/ })).toBeTruthy();
    const contact = screen.getByRole("heading", { name: "Contact" }).closest("section") as HTMLElement;
    const github = await within(contact).findByRole("link", { name: "GitHub" });
    expect(github.getAttribute("href")).toBe("https://github.com/duotkuerduot");
    expect(screen.getAllByText(/Wanjawa, Barack \(2026\)/).length).toBeGreaterThan(0);
  });

  it("about: says so honestly when the no-change guess is the champion", async () => {
    stubFetch({
      "report.json": (body) => {
        const models = (body.models as Json[]).map((m) => ({ ...m, is_champion: m.model_id === "B0" }));
        return { ...body, models, champion: { model_id: "B0", label: "No-change guess", reason: "No model passed" } };
      },
    });
    renderAt("/about");
    expect(await screen.findByText(/no model beat the no-change guess/)).toBeTruthy();
    expect(await screen.findByText("Skill by year: LightGBM")).toBeTruthy();
  });

  it("not-found page", async () => {
    renderAt("/no-such-page");
    expect(await screen.findByText("This page does not exist.")).toBeTruthy();
  });

  it("sample mode: label and a notice on every page", async () => {
    stubFetch({
      "status.json": (body) => ({
        ...body,
        data_mode: "sample",
        dataset: { ...(body.dataset as Json), source: "sample", citation: "nsefc synthetic sample dataset", url: null },
      }),
    });
    for (const path of ["/", "/stocks/SCOM", "/about"]) {
      const view = renderAt(path);
      expect(await screen.findByText("Data through Fri 31 Oct 2025 · Sample data")).toBeTruthy();
      expect(
        screen.getByText("Showing synthetic sample data. Run without --sample to use real NSE data."),
      ).toBeTruthy();
      view.unmount();
    }
  });

  it("imported sessions are labelled", async () => {
    stubFetch({ "status.json": (body) => ({ ...body, data_mode: "historical+imports" }) });
    renderAt("/");
    expect(
      await screen.findByText("Data through Fri 31 Oct 2025, including sessions you imported · Mendeley Data v1"),
    ).toBeTruthy();
  });
});

describe("delisted securities", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("say when the data stops", async () => {
    stubFetch({
      "stocks/KUKZ.json": (body) => ({ ...body, status: "delisted" }),
    });
    renderAt("/stocks/KUKZ");
    expect(await screen.findByText(/has left the market or changed its ticker/)).toBeTruthy();
  });
});
