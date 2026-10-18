import { expect, type Page, test } from "@playwright/test";

// G3-07: a multi-storey building from the map, end to end: draw an area → 4 floors, hospital,
// rooms → check → floor switcher → test → one-floor replay. Screenshots go to docs/screenshots/
// (SHOTS=0 skips them). "Draw an area" needs no map-data server, only the map tiles.
const SHOTS = process.env.SHOTS !== "0";
const shot = async (page: Page, name: string) => {
  if (SHOTS) await page.screenshot({ path: `../docs/screenshots/${name}.png` });
};

test("multi-storey journey: 4-floor hospital from the map to a one-floor replay", async ({ page }) => {
  test.setTimeout(900_000);
  await page.goto("/");
  await page.getByRole("link", { name: /Pick it on the map/ }).click();
  await expect(page).toHaveURL(/\/new\/place$/);
  const map = page.locator(".maplibregl-canvas").first();
  await expect(map).toBeVisible({ timeout: 30_000 });

  // draw the building's outline with two corners
  await page.getByRole("button", { name: "Draw an area" }).click();
  const box = (await map.boundingBox())!;
  await map.click({ position: { x: box.width * 0.44, y: box.height * 0.44 } });
  await map.click({ position: { x: box.width * 0.56, y: box.height * 0.56 } });

  // a building: 4 floors, used as a hospital, rooms and corridors
  await page.getByRole("button", { name: "Building (indoor)" }).click();
  const floors = page.getByLabel("Floors");
  await floors.fill("4");
  await expect(floors).toHaveValue("4");
  await page.getByLabel("Used as").selectOption("hospital");
  await page.getByLabel("Inside").selectOption("rooms");
  // a small headcount keeps the four-floor simulations short (the sim image is amd64; on an ARM
  // laptop it runs emulated and a 250-person baseline takes ten minutes)
  await page.getByLabel("People (optional)").fill(process.env.PEOPLE ?? "60");
  await page.getByRole("button", { name: "Build venue" }).click();
  await expect(page.getByText(/is ready\./)).toBeVisible({ timeout: 120_000 });
  await expect(page.getByText("4 floors").first()).toBeVisible();
  await shot(page, "map-hospital-4f");
  await page.getByRole("button", { name: "Use this venue" }).click();

  // check: four storeys in the floor switcher, one floor alone
  await expect(page).toHaveURL(/\/p\/p_[^/]+\/describe$/, { timeout: 30_000 });
  const id = page.url().split("/p/")[1].split("/")[0];
  try {
    const switcher = page.getByRole("radiogroup", { name: "Floors to show" });
    await expect(switcher.getByRole("radio")).toHaveCount(6); // all, spread apart, 4 floors
    await expect(page.getByRole("heading", { name: "Floors and rooms" })).toBeAttached();
    await expect(page.locator("canvas").first()).toBeVisible();
    await page.waitForTimeout(4000); // let the 3D view draw before the screenshot
    await shot(page, "check-hospital-4f");
    const third = switcher.getByRole("radio").nth(4); // all, spread, F0, F1, F2 → the 2nd floor up
    const floorName = (await third.textContent()) ?? "";
    await third.click();
    await expect(third).toHaveAttribute("aria-checked", "true");
    await page.waitForTimeout(1500);
    await shot(page, "check-hospital-one-floor");
    await switcher.getByRole("radio", { name: "All floors" }).click();

    // test the plan and wait for Your plan
    await page.getByRole("button", { name: "Test this plan" }).click();
    await expect(page).toHaveURL(/\/work\?session=/, { timeout: 30_000 });
    await expect(page).toHaveURL(/\/p\/p_[^/]+\?session=/, { timeout: 840_000 });
    await expect(page.getByRole("region", { name: "Verdict" })).toBeVisible({ timeout: 30_000 });

    // one-floor replay: the replay's floor switcher puts that floor in focus
    await page.getByRole("tab", { name: "Replay" }).click();
    const replay = page.getByRole("region", { name: "Replay" });
    const replaySwitch = replay.getByRole("radiogroup", { name: "Floors to show" });
    await expect(replaySwitch).toBeVisible({ timeout: 30_000 });
    await replaySwitch.getByRole("radio", { name: floorName }).click();
    await expect(replaySwitch.getByRole("radio", { name: floorName })).toHaveAttribute("aria-checked", "true");
    await page.waitForTimeout(3000);
    await replay.scrollIntoViewIfNeeded();
    await shot(page, "plan-hospital-one-floor");
    // multi-storey plans have a Floors tab: one small plan per storey and people per floor over time
    await page.getByRole("tab", { name: /^Floors/ }).click();
    await expect(page.getByTestId("floor-cards").getByRole("listitem")).toHaveCount(4);
    await expect(page.getByRole("heading", { name: "People on each floor" })).toBeVisible({ timeout: 30_000 });
  } finally {
    await page.request.delete(`/api/v1/projects/${id}`);
  }
});
