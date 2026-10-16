import { expect, test } from "@playwright/test";

// S-09: "Check with more seeds" on Your plan repeats the key run and shows the range with each
// run's basis. Needs a real sandbox (the fake one has no simulation to repeat).
test("seed range on Your plan", async ({ page, request }) => {
  test.setTimeout(600_000);
  const health = await (await request.get("/api/v1/health")).json();
  test.skip(health.providers.sandbox.provider === "fake", "the fake sandbox does not simulate");
  const created = await request.post("/api/v1/projects", { data: { template_id: "school_wing", name: "E2E seed check" } });
  const id = (await created.json()).id as string;
  try {
    const started = await request.post("/api/v1/sessions", { data: { project_id: id, config: { max_rounds: 1, attacks_per_round: 1, fixes_per_attack: 1, fix_targets: 1 } } });
    const sid = (await started.json()).id as string;
    await expect.poll(async () => (await (await request.get(`/api/v1/sessions/${sid}`)).json()).status, { timeout: 420_000, intervals: [3000] })
      .toMatch(/finished|stopped/);

    await page.goto(`/p/${id}?session=${sid}`);
    const panel = page.getByTestId("seed-check");
    await expect(panel.getByRole("heading", { name: "Check with more seeds" })).toBeVisible({ timeout: 30_000 });
    await expect(panel.getByText(/^Repeats: /)).toBeVisible();
    await panel.getByLabel("More seeds").selectOption("2");
    await panel.getByRole("button", { name: "Check with more seeds" }).click();
    // the original run plus two seeds: 3 runs in the range
    await expect(panel.getByText(/^95% out in .+ over 3 seeds$/)).toBeVisible({ timeout: 300_000 });
    await expect(panel.getByText(/^Based on 3 × /)).toBeVisible();
    await panel.getByText("Each run").click();
    await expect(panel.getByText(/^Seed \d+ · the plan's own run$/)).toBeVisible();
    await expect(panel.getByRole("listitem")).toHaveCount(3);
    // repeating the check reuses the runs it has: the button now adds seeds
    await expect(panel.getByRole("button", { name: "Add more seeds" })).toBeEnabled();
  } finally {
    await request.delete(`/api/v1/projects/${id}`);
  }
});
