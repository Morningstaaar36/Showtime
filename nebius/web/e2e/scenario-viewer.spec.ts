import { expect, test } from "@playwright/test";

// G3-06: Your plan lists every tested scenario with its verdict; clicking one plays it, and the
// timeline marks and captions what happens ("… blocked at 1:00"). Replays need a real sandbox.
test("scenario viewer: list, play a scenario, timeline caption", async ({ page, request }) => {
  test.setTimeout(600_000);
  const health = await (await request.get("/api/v1/health")).json();
  const created = await request.post("/api/v1/projects", { data: { template_id: "school_wing", name: "E2E scenario viewer" } });
  const id = (await created.json()).id as string;
  try {
    const started = await request.post("/api/v1/sessions", { data: { project_id: id, config: { max_rounds: 1, attacks_per_round: 3, fixes_per_attack: 1, fix_targets: 1 } } });
    const sid = (await started.json()).id as string;
    await expect.poll(async () => (await (await request.get(`/api/v1/sessions/${sid}`)).json()).status, { timeout: 540_000, intervals: [3000] })
      .toMatch(/finished|stopped/);

    await page.goto(`/p/${id}?session=${sid}`);
    // the Scenarios tab shows them as cards; the Replay tab lists them next to the 3D replay
    await page.getByRole("tab", { name: /^Scenarios/ }).click();
    await expect(page.getByTestId("scenario-gallery").getByRole("listitem").first()).toBeVisible({ timeout: 30_000 });
    await page.getByRole("tab", { name: "Replay" }).click();
    const list = page.getByTestId("scenarios");
    await expect(list.getByRole("heading", { name: "Every scenario the AI tested" })).toBeVisible({ timeout: 30_000 });
    await expect(list.getByRole("button", { name: /Your plan as drawn/ })).toBeVisible();
    // the plan as drawn plus each attack (at least one) carry a verdict
    expect(await list.getByRole("button").count()).toBeGreaterThanOrEqual(2);
    await expect(list.getByText(/^(Holds|Breaks|Preview only|Not confirmed)$/).first()).toBeVisible();

    if (health.providers.sandbox.provider === "fake") return; // no trajectories to replay
    // play the first attack
    const attack = list.getByRole("button").filter({ hasNotText: "Your plan as drawn" }).filter({ hasText: /95% out in/ }).first();
    const title = (await attack.locator("span.font-medium").first().textContent()) ?? "";
    await attack.click();
    await expect(attack).toHaveAttribute("aria-pressed", "true");
    await expect(attack.getByText("Playing")).toBeVisible();
    const replay = page.getByRole("region", { name: /replay/i });
    await expect(replay.getByText(title, { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Back to before and after" })).toBeVisible();

    // seek to the first event marker: its caption shows over the replay
    const marker = page.locator("span.rotate-45").first();
    await expect(marker).toBeAttached({ timeout: 20_000 });
    const slider = page.getByRole("slider", { name: "Replay time" });
    const track = (await slider.locator("xpath=ancestor::span[contains(@class,'touch-none')]").first().boundingBox())!;
    const m = (await marker.boundingBox())!;
    await page.mouse.click(m.x + m.width / 2 + 2, track.y + track.height / 2);
    await expect(replay.getByText(/ at \d+:\d\d|\(\d+:\d\d\)/).first()).toBeVisible({ timeout: 10_000 });
  } finally {
    await request.delete(`/api/v1/projects/${id}`);
  }
});
