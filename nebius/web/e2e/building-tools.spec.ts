import { expect, type Page, test } from "./fixtures";

// G3-01: the building tools in Expert view. Every step is a saved version, so the journey checks
// the saved venue through the API as well as what the screen says.
const rect = (x: number, y: number, w: number, h: number) => [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];

async function venueOf(page: Page, id: string) {
  return (await (await page.request.get(`/api/v1/projects/${id}`)).json()).version.venue;
}

test("building tools: add a floor, stairs and a room, then undo and redo", async ({ page, request }) => {
  const created = await request.post("/api/v1/projects", { data: { name: "E2E building tools", venue: {
    venue_id: "e2e_building", name: "Clinic", mode: "indoor",
    floors: [{ floor_id: "F0", elevation_m: 0, walkable: rect(0, 0, 24, 14), obstacles: [],
               exits: [{ id: "E1", polygon: rect(10, 0.02, 2, 0.4), width_m: 2 }],
               zones: [{ id: "Z1", polygon: rect(2, 3, 12, 8), people: 40 }] }],
    stairs: [] } } });
  expect(created.status()).toBe(201);
  const id = (await created.json()).id as string;
  try {
    await page.goto(`/p/${id}/expert`);
    const rail = page.getByRole("group", { name: "Building" });
    await expect(rail.getByRole("button", { name: "Draw wall" })).toBeVisible({ timeout: 20_000 });

    // a floor on top, named in the dialog
    await rail.getByRole("button", { name: /^Floor to edit: Ground floor/ }).click();
    await page.getByRole("button", { name: "Add floor" }).click();
    const dialog = page.getByRole("dialog", { name: "Add a floor" });
    await dialog.getByLabel("Name").fill("Gallery");
    await dialog.getByRole("button", { name: "Add floor" }).click();
    await expect(page.getByText(/Added Gallery · saved as version 2/)).toBeVisible({ timeout: 20_000 });
    await expect(rail.getByRole("button", { name: /^Floor to edit: Gallery/ })).toBeVisible();

    // stairs from the gallery down to the ground floor, placed with the keyboard and typed numbers
    await page.locator("body").press("s");
    const stairs = page.getByRole("region", { name: "Add stairs" });
    await expect(stairs.getByText("Connects Gallery and Ground floor.")).toBeVisible();
    await stairs.getByLabel("East (m)").fill("20");
    await stairs.getByLabel("North (m)").fill("7");
    await stairs.getByRole("button", { name: "Add stairs" }).click();
    await expect(page.getByText(/Added stairs · saved as version 3/)).toBeVisible({ timeout: 20_000 });

    // a room on the gallery, from the room tool's typed corner and size
    await rail.getByRole("button", { name: "Add room" }).click();
    const room = page.getByRole("region", { name: "Add room" });
    await room.getByLabel("Name (optional)").fill("Ward A");
    await room.getByLabel("People inside (optional)").fill("12");
    await room.getByLabel("East (m)").fill("2");
    await room.getByLabel("North (m)").fill("3");
    await room.getByLabel("Width, east–west (m)").fill("6");
    await room.getByLabel("Depth, north–south (m)").fill("4");
    await room.getByRole("button", { name: "Add room" }).click();
    await expect(page.getByText(/Added Ward A · saved as version 4/)).toBeVisible({ timeout: 20_000 });

    let venue = await venueOf(page, id);
    expect(venue.floors).toHaveLength(2);
    const gallery = venue.floors.find((f: { name: string | null }) => f.name === "Gallery");
    expect(gallery).toBeTruthy();
    expect(venue.stairs).toHaveLength(1);
    expect(venue.stairs[0]).toMatchObject({ from_floor: gallery.floor_id, to_floor: "F0" });
    expect(gallery.obstacles.filter((o: { kind: string }) => o.kind === "wall").length).toBeGreaterThan(0);
    expect(gallery.zones.some((z: { people: number }) => z.people === 12)).toBeTruthy();

    // undo removes the room (a new version), redo brings it back
    await page.keyboard.press("Escape");
    await page.getByRole("banner").getByRole("button", { name: "Undo" }).click();
    await expect.poll(async () => (await venueOf(page, id)).floors.find((f: { name: string | null }) => f.name === "Gallery").zones.length).toBe(0);
    await page.getByRole("banner").getByRole("button", { name: "Redo" }).click();
    await expect.poll(async () => (await venueOf(page, id)).floors.find((f: { name: string | null }) => f.name === "Gallery").zones.length).toBe(1);
    venue = await venueOf(page, id);
    expect(venue.stairs).toHaveLength(1);
  } finally {
    await request.delete(`/api/v1/projects/${id}`);
  }
});
