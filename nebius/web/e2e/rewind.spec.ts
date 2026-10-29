import { expect, type APIRequestContext, test } from "./fixtures";

// Rewind the worst moment and stress test at scale on Your plan. Works with the fake
// providers (every branch is a preview run) and with a real model and simulator.
const created: string[] = [];

test.afterAll(async ({ request }) => {
  for (const id of created) await request.delete(`/api/v1/projects/${id}`);
});

async function testedProject(request: APIRequestContext): Promise<{ pid: string; sid: string }> {
  const p = await (await request.post("/api/v1/projects", { data: { name: "E2E rewind", template_id: "school_wing" } })).json();
  created.push(p.id);
  const config = { max_rounds: 1, attacks_per_round: 3, fixes_per_attack: 2, fix_targets: 1 };
  const s = await (await request.post("/api/v1/sessions", { data: { project_id: p.id, config } })).json();
  await expect.poll(async () => (await (await request.get(`/api/v1/sessions/${s.id}`)).json()).status,
    { timeout: 480_000, intervals: [2000] }).not.toBe("running");
  return { pid: p.id, sid: s.id };
}

test("rewind the worst moment and stress test at scale on Your plan", async ({ page, request }) => {
  test.setTimeout(900_000);
  const { pid, sid } = await testedProject(request);
  // both checks run in sandboxes, so they sit on Expert view's Sandboxes tab, open
  await page.goto(`/p/${pid}/expert/analysis?session=${sid}&tab=sandboxes`);
  await expect(page.getByTestId("sandboxes-tab")).toBeVisible({ timeout: 30_000 });

  const rewind = page.getByRole("region", { name: "Rewind the worst moment" });
  await expect(rewind).toBeVisible({ timeout: 30_000 });
  await rewind.getByRole("button", { name: "Rewind the worst moment" }).click();
  const table = rewind.getByRole("table");
  await expect(table.getByRole("rowheader", { name: /Do nothing/ })).toBeVisible({ timeout: 240_000 });
  await expect(rewind.getByText(/Best from this second|No response did better/)).toBeVisible({ timeout: 240_000 });
  await expect(rewind.getByText(/Rewound to .* into the event/)).toBeVisible();
  // every branch says what its numbers are based on
  await expect(table.getByText(/Preview \(no simulator\)|simulation|Instant estimate/).first()).toBeVisible();
  expect(await table.getByRole("row").count()).toBeGreaterThanOrEqual(3);
  // every column fits in the panel: none is cut off at its edge
  const panel = (await rewind.boundingBox())!;
  const last = (await table.getByRole("columnheader").last().boundingBox())!;
  expect(last.x + last.width).toBeLessThanOrEqual(panel.x + panel.width);
  await expect(rewind.getByText(/started from checkpoint run r_/)).toBeVisible();

  const stress = page.getByRole("region", { name: "Stress test at scale" });
  await stress.getByLabel("Random crowds per test").selectOption("1");
  await stress.getByRole("button", { name: "Run stress test at scale" }).click();
  await expect(stress.getByText(/Finished: (\d+) of \1 done/)).toBeVisible({ timeout: 240_000 });
  await expect(stress.getByRole("table").getByText(/Holds|Breaks the plan/).first()).toBeVisible();
});
