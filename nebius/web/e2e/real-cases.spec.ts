import { expect, test } from "@playwright/test";

// A real case opens its one project: a double click on the tile never builds or opens it twice.

test("a double click on a real case opens its project once", async ({ page, request }) => {
  const cases = (await (await request.get("/api/v1/real_cases")).json()) as { id: string; project_id: string | null }[];
  const built = cases.find((c) => c.project_id);
  test.skip(!built, "no real case has been built yet (opening one needs the model)");
  const before = ((await (await request.get("/api/v1/projects")).json()) as unknown[]).length;
  const opens: string[] = [];
  page.on("request", (r) => { if (r.method() === "POST" && r.url().includes("/real_cases/")) opens.push(r.url()); });

  await page.goto("/");
  const tile = page.getByTestId(`real-case-${built!.id}`);
  await tile.scrollIntoViewIfNeeded();
  await tile.dblclick();
  await expect(page).toHaveURL(new RegExp(`/p/${built!.project_id}`));
  await expect(page.getByTestId("real-case-card")).toBeVisible();
  expect(opens).toEqual([]); // a case built before is opened, not rebuilt
  expect(((await (await request.get("/api/v1/projects")).json()) as unknown[]).length).toBe(before);
});
