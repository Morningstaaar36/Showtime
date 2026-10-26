import { expect, test } from "@playwright/test";

// The sticky header stays on top: the 3D view's floating panels (the floor switch) scroll under
// it instead of drawing over it. AI at work of a finished test on a venue with several floors.
test("the floor switch scrolls under the sticky header", async ({ page, request }) => {
  const projects = (await (await request.get("/api/v1/projects")).json()) as { id: string }[];
  let target: { pid: string; sid: string } | null = null;
  for (const p of projects) {
    const floors = (await (await request.get(`/api/v1/projects/${p.id}`)).json()).version?.venue?.floors?.length ?? 0;
    if (floors < 2) continue;
    const res = await (await request.get(`/api/v1/projects/${p.id}/sessions`)).json();
    const done = (Array.isArray(res) ? res : res.sessions ?? []).find((s: { status: string }) => s.status === "finished");
    if (done) { target = { pid: p.id, sid: done.id }; break; }
  }
  test.skip(!target, "no finished test on a venue with several floors");
  await page.setViewportSize({ width: 1280, height: 700 });
  await page.goto(`/p/${target!.pid}/work?session=${target!.sid}`);
  const floors = page.getByRole("radiogroup", { name: "Floors to show" }).first();
  await expect(floors).toBeVisible({ timeout: 30_000 });
  // scroll the floor switch to the very top of the window, under the sticky header
  await floors.evaluate((el) => el.scrollIntoView({ block: "start" }));
  const header = (await page.locator("header").first().boundingBox())!;
  const box = (await floors.boundingBox())!;
  expect(box.y).toBeLessThan(header.y + header.height);
  const topmost = await page.evaluate(([x, y]) => !!document.elementFromPoint(x, y)?.closest("header"),
    [box.x + box.width / 2, Math.max(box.y + 2, header.y + 2)]);
  expect(topmost, "the header is drawn over the floor switch").toBe(true);
});
