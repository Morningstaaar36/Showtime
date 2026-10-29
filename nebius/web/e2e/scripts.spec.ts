import { expect, test } from "./fixtures";

// The Scripts page: a script that tries to reach the network is refused before it runs, and the
// page says why (the sandbox has no network anyway: docs/SANDBOX_PROOF.md).

test("a script that imports socket is refused with its reason", async ({ page, request }) => {
  const created = await (await request.post("/api/v1/projects", { data: { name: "E2E unsafe script", template_id: "school_wing" } })).json();
  try {
    await page.goto(`/p/${created.id}/scripts`);
    await page.getByRole("button", { name: "New script" }).first().click();
    await page.getByRole("textbox", { name: "Code" }).fill("import socket\nsocket.create_connection(('example.org', 80))\n");
    await page.getByRole("button", { name: "Run in sandbox" }).click();
    // the toast says so, and the editor lists each problem under the code
    await expect(page.getByText("Fix these before running:").first()).toBeVisible();
    await expect(page.getByRole("listitem").filter({ hasText: /socket.* is not allowed/ })).toBeVisible();
    await page.screenshot({ path: "../docs/screenshots/step7/scripts-socket-refused.png", fullPage: true });
    // nothing was sent to the sandbox
    const scripts = (await (await request.get(`/api/v1/projects/${created.id}/scripts`)).json()) as { scripts: { last_run: unknown }[] };
    expect(scripts.scripts.every((s) => !s.last_run)).toBeTruthy();
  } finally {
    await request.delete(`/api/v1/projects/${created.id}`);
  }
});
