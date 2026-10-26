import { expect, test } from "@playwright/test";

// "Break it yourself" works without the 3D view: every exit of the venue is a toggle in the
// Simulate panel (keyboard and screen readers included), and blocking one shows the instant
// estimate and "Confirm with simulation". The exit is whichever the venue has first.
test("block an exit from the panel, then reopen it", async ({ page, request }) => {
  const templates = await (await request.get("/api/v1/templates")).json();
  const tpl = (Array.isArray(templates) ? templates : templates.templates)[0];
  const p = await (await request.post("/api/v1/projects", { data: { name: "E2E break it", template_id: tpl.id } })).json();
  try {
    const venue = (await (await request.get(`/api/v1/projects/${p.id}`)).json()).version.venue;
    const exit = venue.floors.flatMap((f: { exits: { id: string; label?: string }[] }) => f.exits)[0];
    await page.goto(`/p/${p.id}/expert/simulate`);
    const toggle = page.getByRole("button", { name: new RegExp(`^${(exit.label ?? exit.id).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`) }).and(page.locator("[aria-pressed]")).first();
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "true");
    await expect(page.getByRole("button", { name: "Confirm with simulation" })).toBeVisible({ timeout: 20_000 });
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
  } finally {
    await request.delete(`/api/v1/projects/${p.id}`);
  }
});
