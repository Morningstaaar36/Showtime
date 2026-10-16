import { expect, type Page, test } from "@playwright/test";

// G3-02: kind of event with its usual people mix, and one area's groups, start delay and route.
const rect = (x: number, y: number, w: number, h: number) => [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];

async function zones(page: Page, id: string) {
  const v = (await (await page.request.get(`/api/v1/projects/${id}`)).json()).version.venue;
  return Object.fromEntries(v.floors[0].zones.map((z: { id: string }) => [z.id, z]));
}

test("event kind, usual people mix and a zone's profile", async ({ page, request }) => {
  const created = await request.post("/api/v1/projects", { data: { name: "E2E zone profile", venue: {
    venue_id: "e2e_ward", name: "Ward block", mode: "indoor",
    floors: [{ floor_id: "F0", elevation_m: 0, walkable: rect(0, 0, 30, 12), obstacles: [],
               exits: [{ id: "E1", polygon: rect(14, 0.02, 2, 0.4), width_m: 2 }],
               zones: [{ id: "ZA", label: "Ward A", polygon: rect(2, 3, 10, 7), people: 30 },
                       { id: "ZB", label: "Ward B", polygon: rect(18, 3, 10, 7), people: 20 }] }],
    routes: [{ id: "R1", label: "Corridor walk", floor_id: "F0", points: [[5, 6], [25, 6]] }],
    stairs: [] } } });
  expect(created.status()).toBe(201);
  const id = (await created.json()).id as string;
  try {
    await page.goto(`/p/${id}/describe`);
    const kind = page.getByTestId("event-kind");
    await kind.getByLabel("Kind of event").selectOption("hospital");
    await expect(page.getByText(/Event kind set to Hospital · saved as version 2/)).toBeVisible({ timeout: 20_000 });
    await expect(kind.getByText(/^Usually: 25% patients in beds/)).toBeVisible();
    await kind.getByRole("button", { name: "Use the usual people mix in every area" }).click();
    await expect(page.getByText(/Applied the usual people mix to 2 areas · saved as version 3/)).toBeVisible({ timeout: 20_000 });
    let z = await zones(page, id);
    expect(z.ZA.groups.map((g: { kind: string }) => g.kind)).toEqual(["bed", "wheelchair", "elderly", "staff"]);
    expect(z.ZB.groups).toHaveLength(4);
    // nothing left to apply
    await expect(kind.getByRole("button", { name: "Use the usual people mix in every area" })).toBeDisabled();

    // one area: fewer patients in beds, a start delay and the corridor route
    await page.getByRole("button", { name: /^Ward A$/ }).click();
    const profile = page.getByTestId("zone-profile");
    await profile.getByLabel("Share of Patients in beds").fill("40");
    await expect(profile.getByText("The other 15% are general adults.")).toBeVisible();
    await profile.getByLabel("Share of Staff").fill("40");
    await expect(profile.getByRole("alert")).toContainText("more than 100%");
    await profile.getByLabel("Share of Staff").fill("10");
    await profile.getByRole("button", { name: "Save people mix" }).click();
    await expect(page.getByText(/Saved who is in Ward A · saved as version 4/)).toBeVisible({ timeout: 20_000 });

    await profile.getByRole("button", { name: "After a delay" }).click();
    await expect(page.getByText(/Saved when Ward A starts moving · saved as version 5/)).toBeVisible({ timeout: 20_000 });
    const delay = profile.getByLabel("Seconds before they move");
    await delay.fill("120");
    await delay.press("Enter");
    await expect(page.getByText(/saved as version 6/)).toBeVisible({ timeout: 20_000 });

    await profile.getByLabel("Route they walk").selectOption("R1");
    await expect(page.getByText(/Saved the route of Ward A · saved as version 7/)).toBeVisible({ timeout: 20_000 });

    z = await zones(page, id);
    expect(z.ZA.groups.find((g: { kind: string }) => g.kind === "bed").share).toBe(0.4);
    expect(z.ZA.groups.find((g: { kind: string }) => g.kind === "staff").share).toBe(0.1);
    expect(z.ZA.pre_movement_s).toBe(120);
    expect(z.ZA.route_id).toBe("R1");
    expect(z.ZB.route_id ?? null).toBeNull();
  } finally {
    await request.delete(`/api/v1/projects/${id}`);
  }
});
