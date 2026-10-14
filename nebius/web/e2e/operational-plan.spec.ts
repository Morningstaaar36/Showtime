import { expect, test } from "@playwright/test";

const rect = (x: number, y: number, w: number, h: number) => [[x,y],[x+w,y],[x+w,y+h],[x,y+h]];

test("guided organizer settings and atomic action preview, replacement and removal", async ({ page, request }) => {
  const created = await request.post("/api/v1/projects", { data: { name: "P2/P3 operational browser fixture", venue: {
    venue_id: "browser_room", name: "Browser room", mode: "indoor", floors: [{ floor_id: "F0", elevation_m: 0, walkable: rect(0,0,12,10), obstacles: [], exits: [{ id: "E1", polygon: rect(4,0.02,2,0.4), width_m: 2 }], zones: [{ id: "Z1", polygon: rect(1,5,8,4), people: 20 }] }], stairs: [] } } });
  expect(created.status()).toBe(201);
  const id = (await created.json()).id;
  try {
    await page.goto(`/p/${id}/describe`);
    await page.getByText("Resources and operational plan", { exact: true }).click();
    const panel = page.getByTestId("operational-plan");
    await panel.getByLabel("New resource ID").fill("stewards");
    await panel.getByRole("button", { name: "Add resource", exact: true }).click();
    await panel.getByLabel("stewards count", { exact: true }).fill("2");
    await panel.getByLabel("New resource ID").fill("radios");
    await panel.getByRole("button", { name: "Add resource", exact: true }).click();
    await panel.getByRole("combobox", { name: "radios kind", exact: true }).selectOption("equipment");
    await panel.getByLabel("New permission ID").fill("venue_permission");
    await panel.getByRole("button", { name: "Add permission", exact: true }).click();
    await panel.getByRole("combobox", { name: "venue_permission status", exact: true }).selectOption("approved");
    await panel.getByRole("button", { name: "Save organizer settings", exact: true }).click();
    await expect(panel.getByRole("alert")).toContainText("source");
    expect((await (await request.get(`/api/v1/projects/${id}/plan`)).json()).version).toBe(1);
    await panel.getByLabel("venue_permission source", { exact: true }).fill("Synthetic organizer exercise");
    await panel.getByLabel("venue_permission recorded by", { exact: true }).fill("Browser test");
    await panel.getByLabel("Declared cost budget", { exact: true }).fill("100");
    await panel.getByRole("button", { name: "Save organizer settings", exact: true }).click();
    await expect(panel.getByText(/Saved version 2/)).toBeVisible();
    await panel.getByLabel("Action ID", { exact: true }).fill("hold");
    await panel.getByLabel("Action description", { exact: true }).fill("Staffed release of the audience");
    await panel.getByLabel("Action end (s)", { exact: true }).fill("30");
    await panel.getByLabel("Release delay (s)", { exact: true }).fill("20");
    await panel.getByLabel("stewards allocation", { exact: true }).fill("3");
    await panel.getByLabel("radios allocation", { exact: true }).fill("1");
    await panel.getByLabel("Action permission IDs", { exact: true }).fill("venue_permission");
    await panel.getByLabel("Action declared cost (USD)", { exact: true }).fill("5");
    await panel.getByRole("button", { name: "Preview action", exact: true }).click();
    await expect(panel.getByRole("status")).toContainText("resource_overallocated");
    expect((await (await request.get(`/api/v1/projects/${id}/plan`)).json()).plan.actions).toHaveLength(0);
    await panel.getByLabel("stewards allocation", { exact: true }).fill("1");
    await expect(panel.getByRole("status")).toHaveCount(0);
    await panel.getByRole("button", { name: "Preview action", exact: true }).click();
    await expect(panel.getByRole("status")).toContainText("Valid proposal — not saved");
    expect((await (await request.get(`/api/v1/projects/${id}/plan`)).json()).plan.actions).toHaveLength(0);
    await panel.getByRole("button", { name: "Apply operational proposal", exact: true }).click();
    await expect(panel.getByText(/Saved version 3/)).toBeVisible();
    await page.reload();
    await page.getByText("Resources and operational plan", { exact: true }).click();
    await expect(panel.getByText("Staffed release of the audience", { exact: true })).toBeVisible();
    await panel.getByRole("button", { name: "Edit action", exact: true }).click();
    await panel.getByLabel("Release delay (s)", { exact: true }).fill("25");
    await panel.getByRole("button", { name: "Preview action", exact: true }).click();
    await panel.getByRole("button", { name: "Apply operational proposal", exact: true }).click();
    await expect(panel.getByText(/Saved version 4/)).toBeVisible();
    const plan = await (await request.get(`/api/v1/projects/${id}/plan`)).json();
    expect(plan.plan.actions).toHaveLength(1);
    expect(plan.plan.actions[0].event.delay_s).toBe(25);
    expect(plan.plan.actions[0].resources).toEqual([{ resource_id: "stewards", quantity: 1 }, { resource_id: "radios", quantity: 1 }]);
    await panel.getByRole("button", { name: "Preview removal", exact: true }).click();
    await panel.getByRole("button", { name: "Apply operational proposal", exact: true }).click();
    await expect(panel.getByText(/Saved version 5/)).toBeVisible();
    expect((await (await request.get(`/api/v1/projects/${id}/plan`)).json()).plan.actions).toHaveLength(0);
  } finally { await request.delete(`/api/v1/projects/${id}`); }
});
