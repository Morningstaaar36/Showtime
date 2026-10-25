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
