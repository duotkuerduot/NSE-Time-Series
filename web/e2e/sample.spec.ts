import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

// End to end: run against `nsefc serve` after `nsefc run --sample`,
// with NSEFC_E2E_URL pointing at the server. The tests read the published API to pick tickers.
async function axe(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.nodes.length}): ${v.help}`);
}

interface Item {
  ticker: string;
  name: string;
  has_forecast: boolean;
}

async function items(page: Page): Promise<Item[]> {
  const status = await (await page.request.get("/api/v1/status.json")).json();
  const stocks = await (await page.request.get(`/api/v1/r/${status.release_id}/stocks.json`)).json();
  return stocks.items as Item[];
}

test("homepage loads with the sample label and notice", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Find an NSE stock");
  await expect(page.getByText(/Data through .* · Sample data/)).toBeVisible();
  await expect(page.getByText("Showing synthetic sample data. Run without --sample to use real NSE data.")).toBeVisible();
  await expect(page.getByText("Biggest gainers")).toBeVisible();
  expect(await axe(page)).toEqual([]);
});

test("search finds a sample ticker and its page shows a forecast", async ({ page }) => {
  const forecast = (await items(page)).find((i) => i.has_forecast);
  expect(forecast).toBeTruthy();
  await page.goto("/");
  await page.getByRole("combobox", { name: "Find an NSE stock" }).fill(forecast!.ticker);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(new RegExp(`/stocks/${forecast!.ticker}$`));
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(forecast!.name);
  await expect(page.getByText(/Model forecast for/)).toBeVisible();
  await expect(page.getByText("80% expected range", { exact: false })).toBeVisible();
  await expect(page.getByText(/Simulated \(backtest\)/).first()).toBeVisible();
  expect(await axe(page)).toEqual([]);
});

test("a stock without a forecast says why", async ({ page }) => {
  const none = (await items(page)).find((i) => !i.has_forecast);
  expect(none).toBeTruthy();
  await page.goto(`/stocks/${none!.ticker}`);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(none!.name);
  await expect(page.getByText(/^No forecast|suspended|paused|not ready|unavailable/).first()).toBeVisible();
});

test("the About page shows results and contact links", async ({ page }) => {
  await page.goto("/about");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("How the forecasts work");
  await expect(page.getByText("Every model, through the same gates")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Contact" })).toBeVisible();
  await expect(page.locator("section", { has: page.getByRole("heading", { name: "Contact" }) }).getByRole("link").first()).toBeVisible();
  expect(await axe(page)).toEqual([]);
});

test("a deep link is served by the app, and unknown API paths are 404", async ({ page }) => {
  const response = await page.goto("/stocks/NOPE");
  expect(response?.status()).toBe(200);
  await expect(page.getByText("There is no NSE stock with ticker NOPE.")).toBeVisible();
  expect((await page.request.get("/api/v1/no-such-file.json")).status()).toBe(404);
});
