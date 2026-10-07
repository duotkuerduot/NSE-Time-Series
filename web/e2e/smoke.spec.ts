import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

// Every page renders from the fixtures and has no serious or critical WCAG 2.1 AA problems
// (ENGINEERING.md 24.9, 28.2).
const PAGES = [
  { path: "/", heading: "Find an NSE stock", text: "Biggest gainers" },
  { path: "/stocks/SCOM", heading: "Safaricom PLC", text: "80% expected range" },
  { path: "/stocks/KUKZ", heading: "Kakuzi Plc", text: "trades too rarely" },
  { path: "/stocks/UCHM", heading: "Uchumi Supermarket Plc", text: "suspended" },
  { path: "/about", heading: "How the forecasts work", text: "not investment advice" },
  { path: "/no-such-page", heading: "This page does not exist.", text: "NSE Forecast" },
];

async function seriousViolations(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.nodes.length}): ${v.help}`);
}

for (const { path, heading, text } of PAGES) {
  test(`${path} renders and passes axe`, async ({ page }) => {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(heading);
    await expect(page.getByText(text, { exact: false }).first()).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });
}

test("a former name finds the current ticker", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("combobox", { name: "Find an NSE stock" }).fill("barclays");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/stocks\/ABSA$/);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Absa");
});
