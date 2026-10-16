import { expect, test } from "@playwright/test";

// G3-05: "Include the surroundings" on the map screen sends surroundings_m with a building.
test("map screen: a drawn building asks for its surroundings", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/new/place");
  const map = page.locator(".maplibregl-canvas").first();
  await expect(map).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: "Draw an area" }).click();
  const box = (await map.boundingBox())!;
  await map.click({ position: { x: box.width * 0.42, y: box.height * 0.42 } });
  await map.click({ position: { x: box.width * 0.58, y: box.height * 0.58 } });
  await page.getByRole("button", { name: "Building (indoor)" }).click();

  const options = page.getByTestId("surroundings");
  await expect(options.getByText("Include the surroundings")).toBeVisible();
  // off by default, and nothing is sent then
  await expect(options.getByRole("slider")).toHaveCount(0);
  await options.getByRole("switch", { name: "Include the surroundings" }).click();
  const slider = options.getByRole("slider", { name: "Distance around the building" });
  await expect(slider).toHaveAttribute("aria-valuenow", "50");
  await slider.focus();
  for (let i = 0; i < 3; i++) await page.keyboard.press("ArrowRight");
  await expect(options.getByText("80 m")).toBeVisible();

  const sent = page.waitForRequest((r) => r.url().endsWith("/api/v1/venues/from-map") && r.method() === "POST");
  await page.getByRole("button", { name: "Build venue" }).click();
  const body = (await sent).postDataJSON();
  expect(body).toMatchObject({ mode: "indoor", surroundings_m: 80 });
});
