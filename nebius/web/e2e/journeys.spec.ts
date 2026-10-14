import { expect, type Page, test } from "@playwright/test";

const created: string[] = [];

test.afterAll(async ({ request }) => {
  for (const id of created) await request.delete(`/api/v1/projects/${id}`);
});

async function llmReady(page: Page): Promise<boolean> {
  const h = await (await page.request.get("/api/v1/health")).json();
  // the fake provider (tests, no model) reports healthy but cannot follow edit requests
  if (h?.providers?.llm?.provider === "fake") return false;
  return Boolean(h?.providers?.llm?.ok ?? h?.llm?.ok);
}

test("open a sample, read its red-team result and its report", async ({ page }) => {
  await page.goto("/projects");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  const sample = page.getByRole("link", { name: /Open .*alley/i }).first();
  await expect(sample).toBeVisible();
  await sample.click();
  await expect(page).toHaveURL(/\/p\/p_/);
  await page.getByRole("link", { name: "Expert view" }).first().click();
  await expect(page).toHaveURL(/\/expert$/);

  await page.getByRole("button", { name: "Red Team", exact: true }).click();
  await expect(page).toHaveURL(/\/redteam$/);
  await expect(page.getByText(/Attacks and fixes/i).first()).toBeVisible({ timeout: 15_000 });

  await page.getByRole("button", { name: "Report", exact: true }).click();
  await expect(page).toHaveURL(/\/report$/);
  const report = page.frameLocator('iframe[title="Report preview"]');
  await expect(report.getByText("Planning aid, not a safety certification.").first()).toBeVisible({ timeout: 20_000 });
});

test("plan a new event: create, edit by text, undo, stress test, block an exit", async ({ page, request }) => {
  await page.goto("/projects");
  await page.getByRole("button", { name: /School wing/ }).first().click();
  await page.getByPlaceholder("Riverside Festival 2026").fill("E2E school drill");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page).toHaveURL(/\/p\/p_.*\/describe$/);
  created.push(page.url().split("/p/")[1].split("/")[0]);
  await page.goto(`/p/${created[created.length - 1]}/expert`);

  if (await llmReady(page)) {
    const box = page.getByLabel("Edit by text");
    await box.fill("add a 2 m exit on the east wall");
    await box.press("Enter");
    await expect(page.getByText(/Added a 2 m exit/).first()).toBeVisible({ timeout: 90_000 });
    await expect(page.getByRole("button", { name: /School wing v2/ })).toBeVisible();
    await page.locator("canvas").first().click({ position: { x: 5, y: 5 } });
    await page.keyboard.press("Control+z");
    // undo saves a new version that restores the previous plan (history is never lost)
    await expect(page.getByRole("banner").getByRole("button", { name: "Redo" })).toBeEnabled();
    await expect(page.getByRole("banner").getByRole("button", { name: "Undo" })).toBeDisabled();
    await expect(page.getByText("door_e1")).toHaveCount(0);
  }

  await page.getByRole("button", { name: "Simulate", exact: true }).click();
  await expect(page).toHaveURL(/\/simulate$/);
  await page.getByRole("button", { name: "Run stress test" }).first().click();
  await expect(page.getByText("Stress test finished").first()).toBeVisible({ timeout: 150_000 });
  const health = await (await request.get("/api/v1/health")).json();
  await expect(page.getByText(health.providers.sandbox.provider === "fake" ? /Preview only/ : /Confirmed by simulation/).first()).toBeVisible();

  // instant estimate through the API used by "Break it yourself"
  const id = created[created.length - 1];
  const res = await request.post(`/api/v1/venues/${id}/tier1`, { data: { blocked_exits: [] } });
  expect(res.ok()).toBeTruthy();
});

test("help lists the keyboard shortcuts and unknown pages explain themselves", async ({ page }) => {
  await page.goto("/help");
  await expect(page.getByText("Run stress test").first()).toBeVisible();
  await page.goto("/definitely-not-here");
  await expect(page.getByRole("link", { name: /projects/i }).first()).toBeVisible();
});

test("guided journey: template, correct and lock, test, review and accept", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Plan a safe event in minutes" })).toBeVisible();
  await page.getByRole("button", { name: /Try a sample/ }).click();
  await page.getByRole("button", { name: /Conference hall, 2 floors/ }).click();
  await expect(page).toHaveURL(/\/describe$/);
  created.push(page.url().split("/p/")[1].split("/")[0]);

  // correct a door numerically, then lock it: its controls become read-only
  await page.getByRole("button", { name: /^South door 1/ }).click();
  const width = page.getByLabel("Width");
  await width.fill("3");
  await width.press("Enter");
  await expect(page.getByText(/South door 1 set to 3.0 m · saved as version 2/)).toBeVisible();
  await page.getByRole("switch", { name: /Lock this item/ }).click();
  await expect(page.getByText(/Locked South door 1 · saved as version 3/)).toBeVisible();
  await expect(page.getByLabel("Width")).toBeDisabled();
  await page.getByRole("button", { name: "Back to the list" }).click();
  await expect(page.getByRole("button", { name: /^South door 1/ }).getByText("Locked")).toBeVisible();

  await page.getByRole("button", { name: "Test this plan" }).click();
  await expect(page).toHaveURL(/\/work\?session=/);
  await expect(page.getByText("Simulating the crowd")).toBeVisible();
  // a test the organizer just started moves on to the plan by itself
  await expect(page).toHaveURL(/\/p\/p_[^/]+\?session=/, { timeout: 170_000 });
  await expect(page.getByRole("region", { name: "Verdict" })).toBeVisible();
  await expect(page.getByText("Evacuation time (95%)")).toBeVisible();
  await expect(page.getByRole("link", { name: "Download report" })).toBeVisible();
  const accept = page.getByRole("button", { name: "Accept these changes" });
  if (await accept.isVisible()) {
    const saved = page.waitForResponse((r) => /\/sessions\/[^/]+\/apply$/.test(r.url()) && r.request().method() === "POST");
    await accept.click();
    const response = await saved;
    expect(response.ok()).toBeTruthy();
    const result = await response.json();
    await expect(page.getByText(`Version ${result.version.version}`, { exact: true })).toBeVisible();
    // Saving provenance/proposed construction or operations can change the full
    // identity. Saving successfully must not imply that older evidence is current.
    await expect(accept).not.toBeVisible();
  }
  // nothing on the simple screens shows machine ids or tier jargon
  await expect(page.locator("main")).not.toContainText(/\bTier\b|run_id|door_s1/);
});

test("old workspace links open Expert view; phone screens never scroll sideways", async ({ page, request }) => {
  const res = await request.post("/api/v1/projects", { data: { template_id: "school_wing" } });
  const { id } = await res.json();
  created.push(id);
  await page.goto(`/p/${id}/simulate`);
  await expect(page).toHaveURL(new RegExp(`/p/${id}/expert/simulate$`));
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ["/", `/p/${id}/describe`, `/p/${id}`]) {
    await page.goto(path);
    await page.waitForTimeout(800);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  }
});
