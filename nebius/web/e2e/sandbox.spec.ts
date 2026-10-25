import { expect, test } from "@playwright/test";

// The sandbox is the core: a person watching the screen can see where the AI's code runs,
// with what limits, and what it stopped.

test("the header shows the sandbox and what it guarantees", async ({ page }) => {
  await page.goto("/");
  const badge = page.getByTestId("sandbox-badge").first();
  await expect(badge).toBeVisible();
  await badge.click();
  const facts = page.getByTestId("sandbox-facts");
  await expect(facts).toContainText("No network");
  await expect(facts).toContainText("Read-only system");
  await page.getByRole("link", { name: "What it stopped in tests" }).click();
  await expect(page).toHaveURL(/\/help#sandbox$/);
  await expect(page.getByRole("heading", { name: "Sandbox", exact: true })).toBeInViewport();
});

test("a Help link to a section opens at that section", async ({ page }) => {
  await page.goto("/help#verdict");
  await expect(page.getByRole("heading", { name: "Reading the verdict" })).toBeInViewport();
});

test("the AI team page names the sandbox and its limits", async ({ page }) => {
  await page.goto("/team");
  await expect(page.getByTestId("team-isolation")).toContainText(/one container per run, no network/i);
});

test("AI at work shows every run's sandbox live, including the scenario script", async ({ page, request }) => {
  test.setTimeout(400_000);
  // Offline mode: rules stand in for the AI, so this needs no model calls; the rule red team
  // still sends one hand-written scenario script into the sandbox
  const created = await (await request.post("/api/v1/projects", { data: { name: "E2E sandbox feed", template_id: "school_wing" } })).json();
  try {
    await page.goto(`/p/${created.id}/describe`);
    await page.getByRole("radio", { name: /Offline/ }).click();
    await page.getByRole("button", { name: "Test this plan" }).click();
    await expect(page).toHaveURL(/\/work\?session=/, { timeout: 30_000 });
    const feed = page.getByTestId("sandbox-feed");
    await expect(feed).toBeVisible();
    await expect(feed.getByTestId("sandbox-row").first()).toBeVisible({ timeout: 60_000 });
    await expect(feed).toContainText(/One container per run, no network/);
    await expect(feed).toContainText(/\d+ of \d+ done/);
    // every run ends in a final state with its time; the script run says what happened to it
    await expect(feed.locator('[data-testid="sandbox-row"][data-state="finished"]').first()).toBeVisible({ timeout: 300_000 });
  } finally {
    await request.delete(`/api/v1/projects/${created.id}`);
  }
});
