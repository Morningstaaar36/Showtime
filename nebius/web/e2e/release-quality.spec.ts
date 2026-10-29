import AxeBuilder from "@axe-core/playwright";
import { expect, type Page, test } from "./fixtures";

// S-02: no console errors on any page; WCAG 2.2 AA (axe) on the three simple screens in light and
// dark; keyboard focus visible on their primary actions; no sideways scroll at phone width.
const AA = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];

let project = "";
let session = "";

test.beforeAll(async ({ request }) => {
  test.setTimeout(600_000);
  const created = await request.post("/api/v1/projects", { data: { template_id: "school_wing", name: "E2E release quality" } });
  project = (await created.json()).id;
  const started = await request.post("/api/v1/sessions", { data: { project_id: project, config: { max_rounds: 1, attacks_per_round: 1, fixes_per_attack: 1, fix_targets: 1 } } });
  session = (await started.json()).id;
  await expect.poll(async () => (await (await request.get(`/api/v1/sessions/${session}`)).json()).status, { timeout: 540_000, intervals: [3000] })
    .toMatch(/finished|stopped/);
});

test.afterAll(async ({ request }) => {
  if (project) await request.delete(`/api/v1/projects/${project}`);
});

function watchConsole(page: Page): string[] {
  const errors: string[] = [];
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${page.url()}: ${m.text().slice(0, 240)}`); });
  page.on("pageerror", (e) => errors.push(`${page.url()}: pageerror ${e.message.slice(0, 240)}`));
  return errors;
}

async function settle(page: Page) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(1200);
}

test("no console errors on any page", async ({ page }) => {
  test.setTimeout(300_000);
  const errors = watchConsole(page);
  const pages = ["/", "/projects", "/welcome", "/settings", "/help", "/new/place", "/nope",
    `/p/${project}/describe`, `/p/${project}/work?session=${session}`, `/p/${project}?session=${session}`,
    `/p/${project}/expert/plan`, `/p/${project}/expert/simulate`, `/p/${project}/expert/redteam`, `/p/${project}/expert/report`,
    `/p/${project}/scripts`];
  for (const path of pages) {
    await page.goto(path);
    await settle(page);
  }
  expect(errors).toEqual([]);
});

for (const theme of ["light", "dark"] as const) {
  test(`WCAG 2.2 AA on the simple screens (${theme})`, async ({ page }) => {
    test.setTimeout(300_000);
    await page.emulateMedia({ colorScheme: theme });
    await page.addInitScript((th) => localStorage.setItem("showtime.prefs.v1", JSON.stringify({ theme: th })), theme);
    const failures: string[] = [];
    for (const path of ["/", "/new/place", `/p/${project}/describe`, `/p/${project}/work?session=${session}`, `/p/${project}?session=${session}`]) {
      await page.goto(path);
      await settle(page);
      // the 3D canvas and the map are pictures, described in text next to them
      const r = await new AxeBuilder({ page }).withTags(AA).exclude("canvas").exclude(".maplibregl-map").analyze();
      for (const v of r.violations) {
        failures.push(`${path} [${v.id}] ${v.help}: ${v.nodes.slice(0, 4).map((n) => n.target.join(" ")).join(" | ")}`);
      }
    }
    expect(failures).toEqual([]);
  });
}

test("keyboard reaches the primary action of each simple screen with a visible focus", async ({ page }) => {
  const focusOutline = async () => page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (!el) return null;
    const cs = getComputedStyle(el);
    return { text: el.textContent?.trim().slice(0, 40) ?? "", outline: cs.outlineStyle !== "none" && cs.outlineWidth !== "0px", ring: cs.boxShadow !== "none" };
  });
  const tabTo = async (name: RegExp, max = 80) => {
    for (let i = 0; i < max; i++) {
      await page.keyboard.press("Tab");
      const f = await focusOutline();
      if (f && name.test(f.text)) return f;
    }
    return null;
  };
  await page.goto("/");
  await settle(page);
  const home = await tabTo(/Pick it on the map/);
  expect(home, "Pick it on the map is reachable by Tab").not.toBeNull();
  expect(home!.outline || home!.ring).toBe(true);

  await page.goto(`/p/${project}/describe`);
  await settle(page);
  const test1 = await tabTo(/Test this plan/, 200);
  expect(test1, "Test this plan is reachable by Tab").not.toBeNull();
  expect(test1!.outline || test1!.ring).toBe(true);

  await page.goto(`/p/${project}?session=${session}`);
  await settle(page);
  const report = await tabTo(/Download report/, 300);
  expect(report, "Download report is reachable by Tab").not.toBeNull();
  expect(report!.outline || report!.ring).toBe(true);
});

test("phone widths: no sideways scroll on the simple screens", async ({ page }) => {
  for (const width of [320, 375, 414]) {
    await page.setViewportSize({ width, height: 800 });
    for (const path of ["/", "/new/place", `/p/${project}/describe`, `/p/${project}/work?session=${session}`, `/p/${project}?session=${session}`, "/help", "/projects"]) {
      await page.goto(path);
      await settle(page);
      const w = await page.evaluate(() => document.documentElement.scrollWidth);
      expect(w, `${path} at ${width} px`).toBeLessThanOrEqual(width);
    }
  }
});
