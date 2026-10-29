import { expect, test } from "./fixtures";

// Evidence: every attack is grounded in a real, cited incident, and its origin is labelled.
// Offline mode (rules for the AI) needs no model calls; web search is off without a key.

test("a test shows its evidence: tool calls, origin badges and the Evidence panel", async ({ page, request }) => {
  test.setTimeout(400_000);
  const created = await (await request.post("/api/v1/projects", { data: { name: "E2E evidence", template_id: "conference_hall_2f" } })).json();
  const venue = (await (await request.get(`/api/v1/projects/${created.id}`)).json()).version.venue;
  const zone = venue.floors[0].zones[0];
  const people = Math.max(5, zone.people - 1 - Math.floor(Math.random() * 40));
  await request.post(`/api/v1/projects/${created.id}/patch`, { data: { patch: { ops: [{ op: "set_people", zone_id: zone.id, people }] } } });
  try {
    await page.goto(`/p/${created.id}/describe`);
    await page.getByText("More options", { exact: true }).click();
    await page.getByRole("radio", { name: /Offline/ }).click();
    await page.getByRole("button", { name: "Test this plan" }).click();
    await expect(page).toHaveURL(/\/work\?session=/, { timeout: 30_000 });
    const tools = page.getByTestId("tool-calls");
    await expect(tools).toContainText(/similar real incidents found/, { timeout: 60_000 });
    await expect(tools).toContainText("Web search is off (add a Tavily key to switch on)");
    await expect(page.getByTestId("origin-badge").first()).toContainText("Incident dataset", { timeout: 120_000 });

    await expect(page).toHaveURL(/\/p\/p_[^/]+\?session=/, { timeout: 300_000 });
    // the evidence is in Expert view's analysis, on its Scenarios tab
    await page.getByRole("link", { name: "More analysis in Expert view" }).click();
    await expect(page).toHaveURL(/\/expert\/analysis\?/);
    await page.getByRole("tab", { name: /Scenarios/ }).click();
    const panel = page.getByTestId("evidence-panel");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("evidence-dataset").locator("li").first()).toContainText(/Grounds: /);
    await expect(panel.getByTestId("search-off")).toBeVisible();
    await expect(panel.getByTestId("evidence-web")).toHaveCount(0); // only with live web results
  } finally {
    await request.delete(`/api/v1/projects/${created.id}`);
  }
});
