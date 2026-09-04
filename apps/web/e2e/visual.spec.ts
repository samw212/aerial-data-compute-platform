/* Visual sweep: every stage at the default viewport, with console errors and
 * failed requests collected per page. Screenshots land in e2e/.artifacts/visual
 * for a human (or a model) to look at; the assertions are that nothing threw. */

import { expect, test, type Page } from "@playwright/test";

const EMAIL = process.env.ADCP_E2E_EMAIL ?? "admin@adcp.local";
const PASSWORD = process.env.ADCP_E2E_PASSWORD ?? "local-dev-password";
const OUT = "e2e/shots";

type Log = { errors: string[]; failed: string[] };

function watch(page: Page): Log {
  const log: Log = { errors: [], failed: [] };
  page.on("console", (m) => {
    if (m.type() === "error") log.errors.push(m.text());
  });
  page.on("pageerror", (e) => log.errors.push(`pageerror: ${e.message}`));
  page.on("requestfailed", (r) => {
    const why = r.failure()?.errorText ?? "";
    if (why === "net::ERR_ABORTED") return; // MapLibre cancels tile loads it no longer needs
    log.failed.push(`${r.method()} ${r.url()} ${why}`);
  });
  page.on("response", (r) => {
    if (r.status() >= 400 && !r.url().includes("/api/auth/me")) log.failed.push(`${r.status()} ${r.url()}`);
  });
  return log;
}

async function signIn(page: Page) {
  await page.goto("/login");
  await page.screenshot({ path: `${OUT}/00-login.png` });
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page).toHaveURL(/\/$/);
}

async function settle(page: Page, ms = 1200) {
  // Not networkidle: the stages poll jobs and health, so idle never comes.
  await page.waitForLoadState("domcontentloaded");
  await page.waitForTimeout(ms);
}

test("every stage renders without console errors", async ({ page }) => {
  test.setTimeout(300_000);
  const log = watch(page);
  await signIn(page);
  await settle(page);
  await page.screenshot({ path: `${OUT}/01-portfolio.png` });

  await page.getByText("Main pitch").click();
  await expect(page).toHaveURL(/\/venues\//);
  await settle(page);
  await page.screenshot({ path: `${OUT}/02-venue.png` });
  const venueUrl = page.url();

  await page.getByRole("button", { name: "Scenarios" }).click();
  await settle(page, 400);
  await page.screenshot({ path: `${OUT}/03-venue-scenarios.png` });

  await page.goto(venueUrl);
  await page.getByText("Survey 2025-11 (synthetic)").click();
  await expect(page).toHaveURL(/\/model$/);
  await settle(page);
  await page.screenshot({ path: `${OUT}/04-model.png` });
  const modelUrl = page.url();

  for (const tab of ["Structures", "Mounts", "Measure"]) {
    const b = page.getByRole("button", { name: tab, exact: true });
    if (await b.count()) {
      await b.first().click();
      await settle(page, 500);
      await page.screenshot({ path: `${OUT}/04-model-${tab.toLowerCase()}.png` });
    }
  }
  const threeD = page.getByRole("button", { name: "3D", exact: true });
  if (await threeD.count()) {
    await threeD.first().click();
    await settle(page, 1800);
    await page.screenshot({ path: `${OUT}/05-model-3d.png` });
  }

  await page.goto(modelUrl.replace(/model$/, "capture"));
  await settle(page);
  await page.screenshot({ path: `${OUT}/06-capture.png` });
  await page.goto(modelUrl.replace(/model$/, "process"));
  await settle(page);
  await page.screenshot({ path: `${OUT}/07-process.png` });

  await page.goto(venueUrl);
  await page.getByRole("button", { name: "Scenarios" }).click();
  await page.getByText("Baseline · 4 corner masts").click();
  await expect(page).toHaveURL(/\/plan$/);
  await settle(page);
  await page.screenshot({ path: `${OUT}/08-plan.png` });
  await page.getByRole("button", { name: "Coverage", exact: true }).nth(1).click();
  await expect(page.getByText(/kernel 1\.1\.0/)).toBeVisible({ timeout: 20_000 });
  await settle(page, 1500);
  await page.screenshot({ path: `${OUT}/09-plan-coverage.png` });
  for (const tab of ["Cameras", "Tents", "Runs"]) {
    const b = page.getByRole("button", { name: tab, exact: true });
    if (await b.count()) {
      await b.first().click();
      await settle(page, 500);
      await page.screenshot({ path: `${OUT}/09-plan-${tab.toLowerCase()}.png` });
    }
  }
  await page.getByRole("button", { name: "3D", exact: true }).click();
  await settle(page, 1800);
  await page.screenshot({ path: `${OUT}/10-plan-3d.png` });

  await page.goto(page.url().replace(/plan$/, "report"));
  await settle(page);
  await page.screenshot({ path: `${OUT}/11-report.png` });

  await page.goto("/jobs");
  await settle(page);
  await page.screenshot({ path: `${OUT}/12-jobs.png` });
  await page.goto("/admin");
  await settle(page);
  await page.screenshot({ path: `${OUT}/13-admin.png` });

  // Narrow viewport: the workbench must not overflow horizontally.
  await page.setViewportSize({ width: 1024, height: 700 });
  await page.goto(venueUrl);
  await settle(page);
  await page.screenshot({ path: `${OUT}/14-venue-1024.png` });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow, "page scrolls horizontally at 1024px").toBe(false);

  expect(log.errors, `console errors:\n${log.errors.join("\n")}`).toEqual([]);
  expect(log.failed, `failed requests:\n${log.failed.join("\n")}`).toEqual([]);
});
