const { test, expect } = require("@playwright/test");
const AxeBuilder = require("@axe-core/playwright").default;
const { pathToFileURL } = require("node:url");
const path = require("node:path");
const fs = require("node:fs/promises");

const root = path.resolve(__dirname, "..");
const url = pathToFileURL(path.join(root, "index.html")).href;

async function setRange(page, id, value) {
  await page.locator(`#${id}`).fill(String(value));
  await page.locator(`#${id}`).dispatchEvent("input");
}

test.beforeEach(async ({ page }) => {
  await page.goto(url);
});

test("offline boot and controls make no network requests or runtime errors", async ({ page, context }) => {
  const requests = [];
  const errors = [];
  page.on("request", (request) => {
    if (/^https?:/.test(request.url())) requests.push(request.url());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  await context.setOffline(true);
  await page.reload();
  await expect(page.locator("#run")).toHaveText("Start experiment");
  await expect(page.locator("#export")).toBeDisabled();
  await page.locator("#single").click();
  await page.locator("#batch").click();
  await expect(page.locator("#count")).toHaveText("1,001");
  await expect(page.locator("#export")).toBeEnabled();
  await expect(page.locator("#error")).toBeHidden();
  expect(requests).toEqual([]);
  expect(errors).toEqual([]);
});

test("physics changes reset the run; rate and sandbox changes preserve it", async ({ page }) => {
  await page.locator("#batch").click();
  await setRange(page, "rate", 300);
  await setRange(page, "notebook-xi", 1);
  await expect(page.locator("#count")).toHaveText("1,000");
  await expect(page.locator("#cohesion")).toHaveText("100%");
  await setRange(page, "which-path", 40);
  await expect(page.locator("#count")).toHaveText("0");
  await expect(page.locator("#cohesion")).toHaveText("84%");
  await expect(page.locator("#equilibrium-residual")).toHaveText("1.000000");
  await setRange(page, "which-path", 100);
  await expect(page.locator("#visibility")).toHaveText("0%");
  await expect(page.locator("#path-entropy")).toHaveText("1.000");
  await expect(page.locator("#mode")).toHaveText("No interference");
  for (const [id, value] of [["wavelength", 750], ["separation", 0.6]]) {
    await page.locator("#single").click();
    await setRange(page, id, value);
    await expect(page.locator("#count")).toHaveText("0");
  }
  await page.locator("#reset").click();
  await expect(page.locator("#notebook-xi")).toHaveValue("1");
  await expect(page.locator("#which-path")).toHaveValue("100");
});

test("sandbox endpoints, weighted residuals and degeneracies are explicit", async ({ page }) => {
  await expect(page.locator("#equilibrium-residual")).toHaveText("0.000000");
  await expect(page.locator("#equilibrium-xi")).toHaveText("0.5000");
  await setRange(page, "notebook-xi", 0);
  await expect(page.locator("#equilibrium-residual")).toHaveText("-1.000000");
  await setRange(page, "notebook-xi", 1);
  await expect(page.locator("#equilibrium-residual")).toHaveText("1.000000");
  await setRange(page, "notebook-particle", 2);
  await expect(page.locator("#equilibrium-xi")).toHaveText("0.6667");
  await setRange(page, "notebook-stewardship", 0);
  await expect(page.locator("#equilibrium-xi")).toHaveText("Not unique");
  await expect(page.locator("#equilibrium-status")).toContainText("No unique");
  await setRange(page, "notebook-stewardship", 1);
  await setRange(page, "notebook-wave", 0);
  await setRange(page, "notebook-particle", 0);
  await expect(page.locator("#equilibrium-xi")).toHaveText("Not unique");
});

test("both notebook sketches are reference only and readable at narrow widths", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.locator("#single").click();
  const section = page.locator("section[aria-labelledby='lagrangian-title']");
  await expect(section.getByRole("heading", { name: "Gauge and spin-connection sketch" })).toBeVisible();
  await expect(section.getByRole("heading", { name: "Gravity and scalar-field sketch" })).toBeVisible();
  await expect(section).toContainText("not evaluated by the simulator");
  await expect(section).toContainText("final matrix contraction are unclear");
  await expect(page.locator("#count")).toHaveText("1");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});

test("chart tables and actual CSV download contain all detections", async ({ page }) => {
  await page.locator("#batch").click();
  await page.locator("#data-details summary").click();
  await expect(page.locator("#bin-data tr")).toHaveCount(120);
  await expect(page.locator("#trace-data tr")).toHaveCount(160);
  const tableTotal = await page.locator("#bin-data tr").evaluateAll((rows) =>
    rows.reduce((sum, row) => sum + Number(row.children[2].textContent), 0));
  expect(tableTotal).toBe(1000);
  const downloadPromise = page.waitForEvent("download");
  await page.locator("#export").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("quantum-light-lab-simulated.csv");
  const csv = await fs.readFile(await download.path(), "utf8");
  expect(csv).toContain("SIMULATED");
  expect(csv).toContain("photons=1000");
  const rows = csv.split("\n").filter((row) => !row.startsWith("#"));
  expect(rows).toHaveLength(121);
  expect(rows.slice(1).reduce((sum, row) => sum + Number(row.split(",")[3]), 0)).toBe(1000);
});

test("start, pause and clear preserve the intended lifecycle", async ({ page }) => {
  await page.locator("#run").click();
  await expect.poll(async () => Number((await page.locator("#count").innerText()).replaceAll(",", ""))).toBeGreaterThan(0);
  await page.locator("#run").click();
  await expect(page.locator("#run")).toHaveText("Start experiment");
  const count = await page.locator("#count").innerText();
  // Advancing the clock verifies no paused animation frame can add photons.
  await page.clock.install();
  await page.clock.runFor(1000);
  await expect(page.locator("#count")).toHaveText(count);
  await page.locator("#reset").click();
  await expect(page.locator("#count")).toHaveText("0");
  await expect(page.locator("#export")).toBeDisabled();
});

test("keyboard and narrow layouts keep native controls accessible", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 800 });
  await page.locator("#notebook-xi").focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.locator("#notebook-xi")).toHaveValue("0.51");
  await expect(page.locator("#notebook-xi")).toHaveAttribute("aria-valuetext", "0.51 (dimensionless)");
  await page.locator("#single").focus();
  await page.keyboard.press("Enter");
  await expect(page.locator("#count")).toHaveText("1");
  const layout = await page.evaluate(() => ({
    width: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    heights: [...document.querySelectorAll(".equilibrium-controls input")]
      .map((input) => input.getBoundingClientRect().height),
  }));
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.width);
  expect(layout.heights.every((height) => height >= 48)).toBe(true);
});

test("reduced motion starts paused and reload resets in-memory state", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.reload();
  await expect(page.locator("#run")).toHaveText("Start experiment");
  await page.locator("#single").click();
  await setRange(page, "notebook-xi", 1);
  await page.reload();
  await expect(page.locator("#count")).toHaveText("0");
  await expect(page.locator("#notebook-xi")).toHaveValue("0.5");
  await expect(page.locator("#equilibrium-residual")).toHaveText("0.000000");
});

test("visibility handler pauses without background catch-up", async ({ page }) => {
  await page.clock.install();
  await page.reload();
  await page.locator("#run").click();
  await page.clock.runFor(1000);
  // Headless engines do not reliably hide tabs; exercise the handler explicitly.
  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, get: () => true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(page.locator("#run")).toHaveText("Start experiment");
  await expect(page.locator("#status")).toContainText("tab is hidden");
  const count = await page.locator("#count").innerText();
  await page.clock.runFor(10000);
  await expect(page.locator("#count")).toHaveText(count);
});

test("unsupported canvas reports an explicit error and disables experiment controls", async ({ page }) => {
  await page.addInitScript(() => {
    HTMLCanvasElement.prototype.getContext = () => null;
  });
  await page.reload();
  await expect(page.locator("#error")).toContainText("does not support 2D canvas");
  await expect(page.locator("#run")).toBeDisabled();
  await expect(page.locator("#which-path")).toBeDisabled();
});

test("JavaScript-disabled mode explains the missing simulation", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  try {
    const page = await context.newPage();
    await page.goto(url);
    await expect(page.locator("#status")).toContainText("Enable JavaScript");
    await expect(page.locator("h1")).toBeVisible();
  } finally {
    await context.close();
  }
});

test("automated accessibility checks cover expanded chart data and definitions", async ({ page }) => {
  await page.locator("#single").click();
  await page.locator("#data-details summary").click();
  await page.locator(".model-notes summary").click();
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(results.violations).toEqual([]);
});
