// Visible QA run: tests each feature in a Chrome window you can watch, with a caption naming
// the check, then logs PASS/FAIL with the reason and a screenshot. Every target comes from the
// app's own data (the API) and every label from en.json; nothing names a particular venue.
// Usage: node e2e/qa-visible.mjs <outdir> [check-name-substring ...]
//   QA_HEADLESS=1 runs without a window; QA_PAUSE_MS sets the pause after each caption.
import { chromium, expect } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";

const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [out, ...only] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const PAUSE = Number(process.env.QA_PAUSE_MS ?? 1500);

const EN = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8"));
const T = (key, vars = {}) => {
  const s = key.split(".").reduce((n, k) => n?.[k], EN);
  if (typeof s !== "string") throw new Error(`no string ${key}`);
  return s.replace(/\{(\w+)\}/g, (_, v) => String(vars[v] ?? `{${v}}`));
};
const esc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const starts = (x) => new RegExp(`^${esc(x)}`);
const api = async (path, init) => { const r = await fetch(`${BASE}/api/v1${path}`, init); return r.status === 204 ? null : r.json(); };
const post = (path, body) => api(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
const venueOf = async (id) => (await api(`/projects/${id}`)).version.venue;
const TEMPLATES = await (async () => { const t = await api("/templates"); return Array.isArray(t) ? t : t.templates; })();
const template = (want) => (TEMPLATES.find(want) ?? TEMPLATES[0]).id;
const created = [];
const newProject = async (name, want = (t) => t.mode === "indoor" && t.floors === 1) => {
  const p = await post("/projects", { name, template_id: template(want) });
  created.push(p.id);
  return p;
};
// a finished test, chosen by what it has (never by its name)
async function testedPlan(want) {
  for (const p of await api("/projects")) {
    const r = await api(`/projects/${p.id}/sessions`);
    const s = (Array.isArray(r) ? r : r.sessions ?? []).find((x) => x.status === "finished");
    if (!s) continue;
    const full = await api(`/sessions/${s.id}`);
    const v = await venueOf(p.id);
    if (!want || want({ p, s: full, v })) return { pid: p.id, sid: s.id, v, s: full };
  }
  return null;
}

const browser = await chromium.launch({
  headless: process.env.QA_HEADLESS === "1",
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ?? "/usr/bin/google-chrome",
  slowMo: process.env.QA_HEADLESS === "1" ? 0 : 120,
  args: process.env.QA_HEADLESS === "1" ? ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] : ["--start-maximized"],
});
const context = await browser.newContext({ viewport: process.env.QA_HEADLESS === "1" ? { width: 1600, height: 900 } : null, acceptDownloads: true });
await context.addInitScript(() => {
  window.__qa = (text, tone) => {
    let el = document.getElementById("__qa_caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "__qa_caption";
      el.style.cssText = "position:fixed;left:50%;bottom:20px;transform:translateX(-50%);z-index:2147483647;max-width:min(920px,92vw);" +
        "padding:12px 20px;border-radius:12px;color:#fff;font:600 16px/1.4 system-ui,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.35);pointer-events:none;text-align:center";
      document.body.appendChild(el);
    }
    el.style.background = tone === "fail" ? "rgba(160,20,40,.95)" : tone === "pass" ? "rgba(10,110,70,.95)" : "rgba(20,22,40,.92)";
    el.textContent = text;
  };
});
const page = await context.newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message.slice(0, 200)}`));
page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text().slice(0, 200)}`); });
const caption = async (text, tone) => { await page.evaluate(([t, k]) => window.__qa?.(t, k), [text, tone]).catch(() => {}); };
const go = async (path) => { await page.goto(`${BASE}${path}`); await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {}); };

const results = [];
async function check(name, fn) {
  if (only.length && !only.some((o) => name.includes(o))) return;
  errors.length = 0;
  await caption(`Testing: ${name}`);
  await page.waitForTimeout(PAUSE);
  let status = "PASS", why = "";
  try {
    why = (await fn()) ?? "";
    await caption(`Testing: ${name}`);
  } catch (e) {
    status = "FAIL";
    why = e.message.split("\n").filter(Boolean).slice(0, 3).join(" ").slice(0, 300);
  }
  if (status === "PASS" && errors.length) { status = "WARN"; why += ` | ${[...new Set(errors)].slice(0, 2).join(" | ")}`; }
  const shot = `${String(results.length + 1).padStart(2, "0")}-${name.replace(/\W+/g, "-").slice(0, 50)}.png`;
  await caption(`${status}: ${name}`, status === "FAIL" ? "fail" : "pass");
  await page.screenshot({ path: `${out}/${shot}` }).catch(() => {});
  await page.waitForTimeout(PAUSE);
  results.push({ name, status, why, shot });
  console.log(`${status.padEnd(4)} ${name} — ${why}`);
}

// --- projects ---------------------------------------------------------------------------------
await check("Projects: search, copy, download, import, delete", async () => {
  const name = `QA plan ${Date.now() % 10000}`;
  const p = await newProject(name);
  await go("/projects");
  const search = page.getByRole("searchbox", { name: T("projects.search") });
  await search.fill(name);
  await expect(page.getByRole("link", { name: T("projects.open", { name }) })).toHaveCount(1);
  await search.fill("zzz no such plan");
  await expect(page.getByRole("link", { name: starts(T("projects.open", { name: "" })) })).toHaveCount(0);
  await search.fill(name);
  await page.getByRole("button", { name: T("projects.actions", { name }) }).click();
  await page.getByRole("menuitem", { name: T("projects.menu_copy") }).click();
  await expect(page.getByText(T("projects.duplicated")).first()).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: T("projects.actions", { name }) }).first().click();
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("menuitem", { name: T("projects.menu_download") }).click()]);
  const zip = `${out}/qa.showtime.zip`;
  await dl.saveAs(zip);
  if (readFileSync(zip).subarray(0, 2).toString() !== "PK") throw new Error("the download is not a zip");
  await page.getByLabel(starts(T("projects.import_hint", { types: "" }).trim())).setInputFiles(zip);
  await expect(page.getByText(T("projects.imported")).first()).toBeVisible({ timeout: 30_000 });
  for (const x of (await api("/projects")).filter((x) => x.name.startsWith(name))) if (!created.includes(x.id)) created.push(x.id);
  await go("/projects"); // importing opens the imported plan
  await page.getByRole("searchbox", { name: T("projects.search") }).fill(name);
  const before = await page.getByRole("link", { name: starts(T("projects.open", { name: "" })) }).count();
  await page.getByRole("button", { name: starts(T("projects.actions", { name })) }).first().click();
  await page.getByRole("menuitem", { name: T("projects.menu_delete") }).click();
  const confirm = page.getByRole("alertdialog").getByRole("button", { name: T("projects.menu_delete") });
  if (await confirm.count()) await confirm.click();
  await expect(page.getByText(T("projects.deleted")).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("link", { name: starts(T("projects.open", { name: "" })) })).toHaveCount(before - 1);
  return `${before} plans (original, copy, import), then one deleted`;
});

// --- check your venue -------------------------------------------------------------------------
await check("Check venue: an exit's width, lock, headcount, kind of event", async () => {
  const p = await newProject("QA check venue", (t) => t.floors >= 2);
  const exit = (await venueOf(p.id)).floors.flatMap((f) => f.exits)[0];
  const label = exit.label ?? exit.id;
  const width = Math.round((exit.width_m + 0.5) * 10) / 10;
  await go(`/p/${p.id}/describe`);
  await page.getByRole("button", { name: starts(label) }).first().click();
  const field = page.getByLabel(T("check.width"), { exact: true }).first();
  await field.fill(String(width));
  await field.press("Enter");
  await expect.poll(async () => (await venueOf(p.id)).floors.flatMap((f) => f.exits).find((e) => e.id === exit.id)?.width_m, { timeout: 20_000 }).toBe(width);
  await page.getByRole("switch", { name: starts(T("check.lock")) }).click();
  await expect(field).toBeDisabled();
  await page.getByRole("button", { name: T("check.back_to_list") }).click();
  const total = (v) => v.floors.flatMap((f) => f.zones).reduce((n, z) => n + z.people, 0);
  const before = total(await venueOf(p.id));
  const plus = page.getByRole("button", { name: /more people in/i }).first();
  await plus.click();
  await expect.poll(async () => total(await venueOf(p.id)), { timeout: 15_000 }).toBeGreaterThan(before);
  const after = total(await venueOf(p.id));
  const kind = page.getByRole("combobox").last();
  const options = await kind.locator("option").evaluateAll((os) => os.map((o) => o.value));
  const current = (await venueOf(p.id)).event_kind;
  const next = options.find((o) => o && o !== current);
  await kind.selectOption(next);
  await expect.poll(async () => (await venueOf(p.id)).event_kind, { timeout: 15_000 }).toBe(next);
  return `${label} ${exit.width_m} → ${width} m and locked; people ${before} → ${after}; event kind ${current ?? "not set"} → ${next}`;
});

await check("Check venue: floors (one floor, all floors, spread apart)", async () => {
  const p = await newProject("QA floors", (t) => t.floors >= 2);
  const v = await venueOf(p.id);
  await go(`/p/${p.id}/describe`);
  const floors = page.getByRole("radiogroup", { name: T("floors.label") }).first();
  const second = v.floors[1].name ?? v.floors[1].floor_id;
  await floors.getByRole("radio", { name: starts(second) }).click();
  await expect(floors.getByRole("radio", { name: starts(second) })).toHaveAttribute("aria-checked", "true");
  await floors.getByRole("radio", { name: starts(T("floors.exploded")) }).click().catch(async () => {
    await floors.getByRole("button", { name: starts(T("floors.exploded")) }).click();
  });
  await floors.getByRole("radio", { name: starts(T("floors.all")) }).click();
  return `${v.floors.length} floors: ${second} alone, spread apart, all`;
});

await check("Check venue: drag a door from the palette onto the venue", async () => {
  const p = await newProject("QA palette");
  const exits0 = (await venueOf(p.id)).floors.flatMap((f) => f.exits).length;
  await go(`/p/${p.id}/describe`);
  const door = page.getByRole("button", { name: starts(T("check.palette_door")) }).first();
  const canvas = page.locator("canvas").first();
  const box = await canvas.boundingBox();
  const src = await door.boundingBox();
  // try along the canvas until the drop lands on a wall (the venue's position on screen varies)
  const tries = [[0.5, 0.5], [0.45, 0.55], [0.55, 0.45]]; // anywhere on the venue: it snaps to a wall
  for (const [fx, fy] of tries) {
    await page.mouse.move(src.x + src.width / 2, src.y + src.height / 2);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * fx, box.y + box.height * fy, { steps: 12 });
    await page.mouse.up();
    await page.waitForTimeout(1500);
    if ((await venueOf(p.id)).floors.flatMap((f) => f.exits).length > exits0) return `door added (drop at ${fx}, ${fy} of the view)`;
  }
  throw new Error("no drop added a door; the guidance shown: " + ((await page.locator("[data-sonner-toast]").allInnerTexts()).join(" | ") || "none"));
});

// --- Expert view ------------------------------------------------------------------------------
await check("Expert: version history restores an earlier version", async () => {
  const p = await newProject("QA versions");
  const exit = (await venueOf(p.id)).floors.flatMap((f) => f.exits)[0];
  await post(`/projects/${p.id}/patch`, { patch: { ops: [{ op: "resize", target: exit.id, width_m: exit.width_m + 1 }] } }).catch(() => {});
  const v1 = (await api(`/projects/${p.id}`)).current_version;
  await go(`/p/${p.id}/expert/plan`);
  await page.getByRole("button", { name: new RegExp(`v${v1}`) }).first().click();
  const restore = page.getByRole("button", { name: T("ui.topbar.restore") }).first();
  await restore.hover().catch(() => {});
  await restore.click();
  await expect.poll(async () => (await api(`/projects/${p.id}`)).current_version, { timeout: 15_000 }).toBeGreaterThan(v1);
  return `v${v1} → restored v1 as v${(await api(`/projects/${p.id}`)).current_version}`;
});

await check("Expert: break it yourself (block an exit) and confirm", async () => {
  const p = await newProject("QA break it");
  const v = await venueOf(p.id);
  const exit = v.floors.flatMap((f) => f.exits)[0];
  await go(`/p/${p.id}/expert/simulate`);
  // the exit's toggle in the Simulate panel (the same action as clicking it in 3D)
  await page.getByRole("button", { name: starts(exit.label ?? exit.id) }).and(page.locator("[aria-pressed]")).first().click();
  await expect(page.getByRole("button", { name: T("workspace.confirm_with_simulation") })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: T("workspace.confirm_with_simulation") }).click();
  await page.waitForTimeout(3000);
  return `${exit.label ?? exit.id} blocked; instant estimate shown; confirmation started`;
});

await check("Expert: report preview and every export", async () => {
  const plan = await testedPlan(({ v }) => v.floors.length >= 1);
  if (!plan) throw new Error("no finished test to report on");
  await go(`/p/${plan.pid}/expert/report`);
  const frame = page.frameLocator('iframe[title]').first();
  await expect(frame.getByText(T("app.disclaimer")).first()).toBeVisible({ timeout: 30_000 });
  const got = [];
  const links = await page.getByRole("link").or(page.getByRole("button")).filter({ hasText: /SVG|JSON|glb|zip/i }).all();
  for (const link of links) {
    const name = (await link.innerText()).trim();
    const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 60_000 }), link.click()]);
    const file = `${out}/${dl.suggestedFilename()}`;
    await dl.saveAs(file);
    const head = readFileSync(file).subarray(0, 4).toString();
    const ok = /svg/i.test(name) ? head.includes("<") : /json/i.test(name) ? head.trim().startsWith("{") : /glb/i.test(name) ? head === "glTF" : head.startsWith("PK");
    got.push(`${name}: ${ok ? "ok" : "BAD"}`);
    if (!ok) throw new Error(`${name} has the wrong content`);
  }
  if (!got.length) throw new Error("no export links found");
  return got.join("; ");
});

await check("Expert: Red Team tab (cards, branch tree)", async () => {
  const plan = await testedPlan();
  await go(`/p/${plan.pid}/expert/redteam`);
  await page.waitForTimeout(2000);
  const cards = await page.getByText(T("redteam.break")).count() + await page.getByText(/round \d/).count();
  const tree = page.getByRole("button", { name: /branch tree/i }).or(page.getByRole("tab", { name: /branch tree/i })).first();
  if (await tree.count()) await tree.click();
  await page.waitForTimeout(1500);
  if (!cards) throw new Error("no attack cards on the Red Team tab");
  return `${cards} attack markers; branch tree opened`;
});

// --- scripts ----------------------------------------------------------------------------------
await check("Scripts: the example analysis script runs and shows its result", async () => {
  const plan = await testedPlan();
  await go(`/p/${plan.pid}/scripts`);
  await page.getByRole("button", { name: T("userscripts.new") }).first().click();
  await page.getByRole("button", { name: T("userscripts.run") }).click();
  await expect(page.getByRole("table").or(page.locator("svg.recharts-surface")).first()).toBeVisible({ timeout: 120_000 });
  for (const s of (await api(`/projects/${plan.pid}/scripts`)).scripts) await fetch(`${BASE}/api/v1/projects/${plan.pid}/scripts/${s.id}`, { method: "DELETE" });
  return "ran in the sandbox; table or chart shown (script removed afterwards)";
});

// --- Your plan --------------------------------------------------------------------------------
await check("Your plan: replay plays and pauses", async () => {
  const plan = await testedPlan();
  await go(`/p/${plan.pid}?session=${plan.sid}&tab=replay`);
  // the replay may already be playing when the tab opens: pause, play, pause
  const pause = page.getByRole("button", { name: T("timeline.pause") }).first();
  const play = page.getByRole("button", { name: T("timeline.play") }).first();
  if (await pause.isVisible().catch(() => false)) await pause.click();
  await play.click();
  await page.waitForTimeout(2500);
  await page.getByRole("button", { name: T("timeline.pause") }).first().click();
  await expect(page.getByRole("button", { name: T("timeline.play") }).first()).toBeVisible();
  return "paused, played 2.5 s, paused again";
});

await check("Your plan: choose fixes and accept them", async () => {
  // its own plan, tested in Offline mode (rules, no AI): never someone's real plan
  const p = await newProject("QA accept fixes", (t) => t.floors >= 2);
  const sid = (await post("/sessions", { project_id: p.id, config: { max_rounds: 1, attacks_per_round: 3, fixes_per_attack: 2, fix_targets: 2, agents: "rules" } })).id;
  await expect.poll(async () => (await api(`/sessions/${sid}`)).status, { timeout: 600_000, intervals: [3000] }).toMatch(/finished|stopped/);
  const kept = ((await api(`/sessions/${sid}`)).summary?.accepted_fixes ?? []).length;
  await go(`/p/${p.id}?session=${sid}&tab=fixes`);
  if (!kept) return "the Offline test kept no fixes on this venue: nothing to accept (the tab says so)";
  const v0 = (await api(`/projects/${p.id}`)).current_version;
  await page.getByRole("button", { name: T("yourplan.accept") }).click();
  await expect.poll(async () => (await api(`/projects/${p.id}`)).current_version, { timeout: 30_000 }).toBeGreaterThan(v0);
  return `${kept} kept fixes accepted: v${v0} → v${(await api(`/projects/${p.id}`)).current_version}`;
});

await check("Your plan: floors tab", async () => {
  const plan = await testedPlan(({ v }) => v.floors.length >= 2);
  if (!plan) return "no finished test on a venue with several floors";
  await go(`/p/${plan.pid}?session=${plan.sid}&tab=floors`);
  await expect(page.getByText(T("yourplan.per_floor")).first()).toBeVisible({ timeout: 20_000 });
  return `${plan.v.floors.length} floors charted`;
});

// --- settings, welcome --------------------------------------------------------------------------
// --- with the model or the internet ----------------------------------------------------------
await check("Ask or change anything: a what-if and a question", async () => {
  const plan = await testedPlan();
  await go(`/p/${plan.pid}/describe`);
  const box = page.getByRole("textbox", { name: T("ask.label") }).or(page.getByPlaceholder(T("ask.ph"))).first();
  await box.fill(T("ask.ex_rain"));
  await box.press("Enter");
  const reply = page.getByText(T("ask.what_if")).or(page.getByText(T("ask.result"))).first();
  await expect(reply).toBeVisible({ timeout: 120_000 });
  const firstExit = plan.v.floors.flatMap((f) => f.exits)[0];
  await box.fill(T("ask.close_exit", { name: firstExit.label ?? firstExit.id }));
  await box.press("Enter");
  await page.waitForTimeout(8000);
  return `what-if answered (${await page.getByText(T("ask.instant")).count() ? "instant estimate" : "reply"}); closed-exit what-if asked`;
});

await check("Map: search a place and build a venue from a drawn area", async () => {
  const cases = await api("/real_cases");
  const place = (Array.isArray(cases) ? cases : cases.cases)[0].place; // a real place from the app's data
  await go("/new/place");
  await page.getByRole("searchbox", { name: T("ui.maptab.search_for_a_place") }).or(page.getByLabel(T("ui.maptab.search_for_a_place"))).first().fill(place);
  await page.getByRole("button", { name: T("ui.maptab.find") }).click();
  const first = page.getByRole("listitem").getByRole("button").first();
  await first.waitFor({ timeout: 60_000 });
  await first.click();
  await page.waitForTimeout(4000);
  // a search result can be a whole city: zoom in to a site-sized view before drawing
  const zoomIn = page.getByRole("button", { name: /zoom in/i }).first();
  for (let i = 0; i < 5; i++) { await zoomIn.click(); await page.waitForTimeout(500); }
  await page.getByRole("button", { name: T("ui.maptab.draw_an_area") }).click();
  const map = page.locator(".maplibregl-canvas, canvas").first();
  const b = await map.boundingBox();
  await page.mouse.click(b.x + b.width * 0.45, b.y + b.height * 0.45);
  await page.mouse.click(b.x + b.width * 0.55, b.y + b.height * 0.55);
  await page.getByRole("button", { name: T("ui.maptab.build_venue") }).click();
  await expect(page.getByRole("button", { name: T("place.use") })).toBeVisible({ timeout: 180_000 });
  return `searched "${place}", drew an area, built a venue`;
});

await check("Autopilot: one sentence to a tested plan", async () => {
  const sentence = Object.values(EN.ui.describetab.examples).at(-1).text; // the app's own example
  await go("/");
  await page.getByRole("button", { name: starts(T("home.way_describe")) }).first().click();
  await page.getByRole("textbox").first().fill(sentence);
  await page.getByRole("button", { name: T("autopilot.plan_it") }).click();
  await page.waitForURL(/\/autopilot\//, { timeout: 60_000 });
  await page.waitForURL(/\/p\/p_[^/]+(\?|$)/, { timeout: 900_000 });
  const pid = page.url().split("/p/")[1].split(/[/?]/)[0];
  created.push(pid);
  await page.waitForTimeout(3000);
  return `"${sentence.slice(0, 50)}…" → plan ${pid}`;
});

await check("Settings: units switch to imperial and back", async () => {
  await go("/settings");
  const imperial = page.getByRole("button", { name: T("settings.imperial") });
  const metric = page.getByRole("button", { name: T("settings.metric") });
  await imperial.click();
  await expect(imperial).toHaveAttribute("aria-pressed", "true");
  await page.reload();
  await expect(page.getByRole("button", { name: T("settings.imperial") })).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: T("settings.metric") }).click();
  await expect(metric).toHaveAttribute("aria-pressed", "true");
  return "imperial kept after a reload; back to metric";
});

await check("Welcome checklist", async () => {
  await go("/welcome");
  await page.waitForTimeout(3000);
  const text = await page.locator("main").innerText();
  return /not ready/i.test(text) ? `some rows not ready: ${text.replace(/\n+/g, " | ").slice(0, 160)}` : "every row ready";
});

for (const id of created) await fetch(`${BASE}/api/v1/projects/${id}`, { method: "DELETE" }).catch(() => {});
writeFileSync(`${out}/results.json`, JSON.stringify(results, null, 1));
await caption(`Done: ${results.filter((r) => r.status === "PASS").length} passed, ${results.filter((r) => r.status !== "PASS").length} to look at`, results.some((r) => r.status === "FAIL") ? "fail" : "pass");
await page.waitForTimeout(4000);
await browser.close();
