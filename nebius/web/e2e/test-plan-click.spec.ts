import { expect, test } from "@playwright/test";

// G3-06: "Test this plan" sometimes started nothing. The "saved as version N" toasts of the edits
// just made sat on top of the button (bottom-right), so the click landed on a toast. Toasts now open
// bottom-left; this repeats the guided journey's edits and checks no toast covers the button.
test("Test this plan is not covered by the toasts of the edits just saved", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: /Try a sample/ }).click();
  await page.getByRole("button", { name: /Conference hall, 2 floors/ }).click();
  await expect(page).toHaveURL(/\/describe$/);
  const id = page.url().split("/p/")[1].split("/")[0];
  try {
    await page.getByRole("button", { name: /^South door 1/ }).click();
    const width = page.getByLabel("Width");
    await width.fill("3");
    await width.press("Enter");
    await expect(page.getByText(/saved as version 2/)).toBeVisible({ timeout: 20_000 });
    await page.getByRole("switch", { name: /Lock this item/ }).click();
    await expect(page.getByText(/saved as version 3/)).toBeVisible({ timeout: 20_000 });
    await page.getByRole("button", { name: "Back to the list" }).click();

    const button = page.getByRole("button", { name: "Test this plan" });
    const b = (await button.boundingBox())!;
    // where toasts stack is fixed by the toaster (they slide in and out, so test its column, not
    // one toast at one moment): it must not share the bottom of the screen with the button
    const toaster = page.locator("[data-sonner-toaster]").first();
    await expect(toaster).toBeAttached();
    const col = await toaster.evaluate((el) => { const r = el.getBoundingClientRect(); return { left: r.left, right: r.right }; });
    const viewport = page.viewportSize()!;
    const nearBottom = b.y + b.height > viewport.height - 260;
    const sharesColumn = col.left < b.x + b.width && b.x < col.right;
    expect(nearBottom && sharesColumn, `toasts stack in x ${col.left}–${col.right}, over the button at x ${b.x}–${b.x + b.width}`).toBe(false);
    const hit = await page.evaluate(([x, y]) => document.elementFromPoint(x, y)?.closest("button")?.textContent ?? null,
      [b.x + b.width / 2, b.y + b.height / 2]);
    expect(hit).toContain("Test this plan");
  } finally {
    await page.request.delete(`/api/v1/projects/${id}`);
  }
});
