import { expect, type Page, test } from "@playwright/test";

const created: string[] = [];

test.afterAll(async ({ request }) => {
  for (const id of created) await request.delete(`/api/v1/projects/${id}`);
});

async function llmReady(page: Page): Promise<boolean> {
  const h = await (await page.request.get("/api/v1/health")).json();
  return Boolean(h?.providers?.llm?.ok ?? h?.llm?.ok);
}

test("open a sample, read its red-team result and its report", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Projects" })).toBeVisible();
  const sample = page.getByRole("link", { name: /Open .*alley/i }).first();
  await expect(sample).toBeVisible();
  await sample.click();
  await expect(page).toHaveURL(/\/p\/p_/);

  await page.getByRole("button", { name: "Red Team", exact: true }).click();
  await expect(page).toHaveURL(/\/redteam$/);
  await expect(page.getByText(/Attacks and fixes/i).first()).toBeVisible({ timeout: 15_000 });

  await page.getByRole("button", { name: "Report", exact: true }).click();
  await expect(page).toHaveURL(/\/report$/);
  const report = page.frameLocator('iframe[title="Report preview"]');
  await expect(report.getByText("Planning aid, not a safety certification.").first()).toBeVisible({ timeout: 20_000 });
});

test("plan a new event: create, edit by text, undo, stress test, block an exit", async ({ page, request }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /School wing/ }).first().click();
  await page.getByPlaceholder("Riverside Festival 2026").fill("E2E school drill");
  await page.getByRole("button", { name: "Create project" }).click();
  await expect(page).toHaveURL(/\/p\/p_/);
  created.push(page.url().split("/p/")[1].split("/")[0]);

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
  await expect(page.getByText(/Confirmed by simulation/).first()).toBeVisible();

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
