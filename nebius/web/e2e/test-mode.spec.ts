import { expect, test } from "@playwright/test";

// The test mode is one choice above "Test this plan": it is remembered, and it decides the
// session settings that are sent.

test("the chosen test mode is remembered and sent with the test", async ({ page, request }) => {
  const created = await (await request.post("/api/v1/projects", { data: { name: "E2E test mode", template_id: "school_wing" } })).json();
  try {
    await page.goto(`/p/${created.id}/describe`);
    const modes = page.getByRole("radiogroup");
    for (const name of ["Quick", "Deep", "Offline", "Standard"]) {
      await modes.getByRole("radio", { name: new RegExp(name) }).click();
      await expect(modes.getByRole("radio", { name: new RegExp(name) })).toHaveAttribute("aria-checked", "true");
    }
    await modes.getByRole("radio", { name: /Quick/ }).click();
    await page.reload();
    await expect(page.getByRole("radio", { name: /Quick/ })).toHaveAttribute("aria-checked", "true");

    // the session request carries the quick settings; the server's answer is an error here, so
    // nothing runs, and the page says what happened instead of spinning
    let sent: { config?: Record<string, unknown> } | null = null;
    await page.route("**/api/v1/sessions", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      sent = route.request().postDataJSON();
      await route.fulfill({ status: 503, contentType: "application/json",
                            body: JSON.stringify({ code: "busy", message: "The sandbox is busy.", hint: "Try again in a moment." }) });
    });
    await page.getByRole("button", { name: "Test this plan" }).click();
    await expect.poll(() => sent).not.toBeNull();
    expect(sent!.config).toMatchObject({ max_rounds: 1, attacks_per_round: 2, agents: "model" });
    await expect(page.getByRole("alert").or(page.getByText(/busy|couldn.t start/i)).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Test this plan" })).toBeEnabled();
  } finally {
    await request.delete(`/api/v1/projects/${created.id}`);
  }
});
