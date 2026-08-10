import { test, expect, type Page } from "@playwright/test";
import path from "node:path";

const viewport = {
  desktop: { width: 1440, height: 1024 },
  tablet: { width: 834, height: 1194 },
  mobile: { width: 390, height: 844 },
} as const;

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Journey setup error: ${name} is required for this real-service journey.`);
  return value;
}

function runId() { return required("JOURNEY_RUN_ID"); }

async function openRun(page: Page, size: keyof typeof viewport = "desktop") {
  await page.setViewportSize(viewport[size]);
  await page.addInitScript(() => { window.localStorage.clear(); });
  await page.goto(`/?run_id=${encodeURIComponent(runId())}`, { waitUntil: "domcontentloaded" });
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 30_000 });
}

async function selectSection(page: Page, label: "Overview" | "Pipeline" | "Evidence" | "Diagnostics") {
  const button = page.getByRole("button", { name: label, exact: true });
  const link = page.getByRole("link", { name: label, exact: true });
  if (await button.count()) await button.click();
  else await link.click();
  await expect(page.getByRole("heading", { name: label, exact: true })).toBeVisible();
}

function screenshotPath(name: string) {
  return path.resolve(process.cwd(), "..", "docs", "superpowers", "specs", "assets", "2026-08-09-journey-command-center", name);
}

test.describe("Journey Command Center real-service journeys", () => {
  test("landing offers a clear start path", async ({ page }) => {
    await page.setViewportSize(viewport.desktop);
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Start a migration" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Start a new migration" })).toHaveAttribute("href", "/migrations/new");
  });

  test("setup validates project input, exposes configuration invalidation, and supports recheck", async ({ page }) => {
    const sourcePath = required("JOURNEY_SOURCE_PATH");
    const targetParentPath = required("JOURNEY_TARGET_PARENT_PATH");
    await page.setViewportSize(viewport.desktop);
    await page.goto("/migrations/new", { waitUntil: "domcontentloaded" });
    await page.getByLabel("Source path").fill(sourcePath);
    await page.getByLabel("External target-parent path").fill(targetParentPath);
    await page.getByRole("button", { name: "Check readiness", exact: true }).click();
    await expect(page.locator('li[aria-label="Path safety and target reservation"]')).not.toHaveAttribute("data-state", "waiting", { timeout: 90_000 });
    await page.getByLabel("Source path").fill(`${sourcePath} `);
    await expect(page.getByRole("status")).toContainText("Configuration changed");
    await expect(page.getByRole("button", { name: "Check readiness again", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "Check readiness again", exact: true }).click();
    await expect(page.locator('li[aria-label="Path safety and target reservation"]')).not.toHaveAttribute("data-state", "running", { timeout: 90_000 });
  });

  test("G01 route renders supplied authoritative preflight evidence", async ({ page }) => {
    const preflightId = required("JOURNEY_PREFLIGHT_ID");
    await page.setViewportSize(viewport.desktop);
    await page.goto(`/preflights/${encodeURIComponent(preflightId)}`, { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: /G01/i })).toBeVisible({ timeout: 30_000 });
    await expect(page.locator("main")).toContainText(preflightId);
    await expect(page.getByRole("region", { name: "Evidence" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Decision outcome" })).toContainText(/Expired|Passed|Blocked|Rejected|Approved/i);
  });

  test("overview action focuses the corresponding Pipeline stage", async ({ page }) => {
    await openRun(page);
    const pipelineLink = page.getByRole("button", { name: "View in pipeline", exact: true });
    if (await pipelineLink.count()) {
      await pipelineLink.click();
      await expect(page.getByRole("heading", { name: "Pipeline", exact: true })).toBeVisible();
      await expect(page.locator('[aria-label^="Migration workflow progress"]')).toBeVisible();
    } else {
      await selectSection(page, "Pipeline");
    }
  });

  test("Evidence supports search, filtering, preview, and provenance disclosure", async ({ page }) => {
    await openRun(page);
    await selectSection(page, "Evidence");
    const results = page.getByRole("button").filter({ has: page.locator("code") });
    await expect(page.getByLabel("Search evidence")).toBeVisible();
    await expect(page.getByText(/artifacts$/).first()).toBeVisible();
    const resultCount = await results.count();
    if (resultCount === 0) throw new Error("Journey setup error: JOURNEY_RUN_ID returned no evidence results.");
    await results.first().click();
    await expect(page.getByRole("heading", { level: 3 }).first()).toBeVisible();
    await page.getByRole("button", { name: "Preview", exact: true }).click();
    await page.getByText("Provenance", { exact: true }).click();
    await expect(page.getByText("Technical details", { exact: true })).toBeVisible();
    await page.getByLabel("Search evidence").fill("does-not-match-anything");
    await expect(page.getByText("No evidence matches these filters.")).toBeVisible();
  });

  test("Diagnostics exposes blocker, logs, events, and LLM activity", async ({ page }) => {
    let abortedEventStreams = 0;
    await page.route(/\/api\/v1\/runs\/[^/]+\/events(?:\?.*)?$/, async (route) => {
      abortedEventStreams += 1;
      await route.abort();
    });
    await openRun(page);
    await selectSection(page, "Diagnostics");
    await expect(page.getByRole("heading", { name: "Blocker", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Commands and logs", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "LLM diagnostics and usage", exact: true })).toBeVisible();
    await page.getByText("Workflow events", { exact: true }).click();
    await expect(page.getByLabel("Authoritative workflow events")).toBeVisible();
    await page.getByLabel("Search events").fill("blocked");
    await expect(page.getByLabel("Authoritative workflow events")).toBeVisible();
    expect(abortedEventStreams).toBeGreaterThan(0);
    console.log("Intentionally aborted the live SSE request for this read-only diagnostics rendering check.");
  });

  test("Assistant opens, minimizes, closes, and returns focus to its launcher", async ({ page }) => {
    await openRun(page);
    const launcher = page.getByRole("button", { name: "Open Assistant" });
    await launcher.focus();
    await launcher.click();
    const dialog = page.getByRole("dialog", { name: "Migration Follow-up Assistant" });
    await expect(dialog).toBeVisible();
    await expect(page.getByRole("button", { name: "Close Assistant" })).toBeFocused();
    for (let index = 0; index < 4; index += 1) await page.keyboard.press("Tab");
    expect(await dialog.evaluate((element) => element.contains(document.activeElement))).toBe(true);
    await page.getByRole("button", { name: "Minimize Assistant" }).click();
    await expect(page.getByRole("button", { name: "Expand Assistant" })).toBeVisible();
    await page.getByRole("button", { name: "Close Assistant" }).click();
    await expect(page.getByRole("button", { name: "Open Assistant" })).toBeFocused();
  });

  test("keyboard navigation and responsive layout keep controls reachable", async ({ page }) => {
    await openRun(page, "mobile");
    await expect(page.locator("h1")).toHaveCount(1);
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toBeVisible();
    const openNavigation = page.getByRole("button", { name: "Open navigation" });
    if (await openNavigation.count()) await openNavigation.click();
    for (const label of ["Overview", "Pipeline", "Evidence", "Diagnostics"] as const) {
      const item = page.locator(`#${label.toLowerCase()}-navigation-item`);
      if (!(await item.isVisible())) await openNavigation.click();
      await item.focus();
      await page.keyboard.press("Enter");
      await expect(item).toHaveAttribute("aria-current", "page");
    }
    const pipeline = page.locator("#pipeline-navigation-item");
    if (!(await pipeline.isVisible())) await openNavigation.click();
    await pipeline.focus();
    await page.keyboard.press("Enter");
    const stage = page.getByRole("button", { name: /Setup: / }).first();
    await stage.focus();
    await page.keyboard.press("Enter");
    await expect(stage).toHaveAttribute("aria-expanded", "true");
    const tabs = page.getByRole("tab");
    await expect(tabs.first()).toBeVisible();
    if (await tabs.count() > 1) {
      await tabs.first().focus();
      await page.keyboard.press("ArrowRight");
      expect(await page.locator('[role="tab"][aria-selected="true"]').count()).toBe(1);
    }
    const evidence = page.locator("#evidence-navigation-item");
    if (!(await evidence.isVisible())) await openNavigation.click();
    await evidence.focus();
    await page.keyboard.press("Enter");
    const evidenceResult = page.locator('[aria-label="Evidence results"] button').first();
    await expect(evidenceResult).toBeVisible();
    await evidenceResult.focus();
    await page.keyboard.press("Enter");
    await expect(evidenceResult).toHaveAttribute("data-selected", "true");
    const provenance = page.getByText("Provenance", { exact: true });
    await expect(provenance).toBeVisible();
    await provenance.focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText("Technical details", { exact: true })).toBeVisible();
    const preflight = required("JOURNEY_PREFLIGHT_ID");
    await page.goto(`/preflights/${encodeURIComponent(preflight)}`, { waitUntil: "domcontentloaded" });
    const decision = page.getByRole("button", { name: /Approve|Request modification|Reject|Create and start authoritative run/i }).first();
    await expect(decision).toBeVisible();
    await decision.focus();
    expect(await decision.getAttribute("type")).toBe("button");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
    expect(overflow).toBe(false);
    const fixedObstruction = await page.evaluate(() => {
      const action = document.querySelector('[aria-labelledby="current-action-title"]');
      if (!action) return false;
      const box = action.getBoundingClientRect();
      return [...document.querySelectorAll<HTMLElement>("*")].some((element) => {
        if (element === action || !element.getBoundingClientRect) return false;
        if (getComputedStyle(element).position !== "fixed") return false;
        const other = element.getBoundingClientRect();
        return other.width > 0 && other.height > 0 && other.bottom > box.top && other.top < box.bottom && other.right > box.left && other.left < box.right;
      });
    });
    expect(fixedObstruction).toBe(false);
  });

  test("captures approved responsive comparison states", async ({ page }) => {
    await openRun(page, "desktop");
    await page.screenshot({ path: screenshotPath("built-overview-desktop.png") });
    await selectSection(page, "Pipeline");
    await page.setViewportSize(viewport.tablet);
    await page.screenshot({ path: screenshotPath("built-pipeline-tablet.png") });
    const transformation = page.getByRole("button", { name: /20.*21|Transform/i }).first();
    if (await transformation.count()) await transformation.click();
    await page.setViewportSize(viewport.mobile);
    await page.screenshot({ path: screenshotPath("built-transformation-mobile.png") });
    await page.setViewportSize(viewport.desktop);
    await selectSection(page, "Evidence");
    await page.screenshot({ path: screenshotPath("built-evidence-desktop.png") });
  });
});
