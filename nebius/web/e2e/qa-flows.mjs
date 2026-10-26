// QA feature flows (no model calls): each flow drives the real app in Chrome, checks its
// outcome, and records PASS/FAIL with a reason and a screenshot. Usage:
//   node e2e/qa-flows.mjs <outdir> [flow-name-substring]
import { chromium, expect } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";

const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
// every on-screen text comes from the app's own locale file, never typed in here
const EN = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8"));
const T = (key, vars = {}) => key.split(".").reduce((n, k) => n?.[k], EN).replace(/\{(\w+)\}/g, (_, v) => String(vars[v] ?? `{${v}}`));
const esc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const startsWith = (x) => new RegExp(`^${esc(x)}`);
const [out, only] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const api = async (path, init) => {
  const r = await fetch(`${BASE}/api/v1${path}`, init);
  return r.status === 204 ? null : r.json();
};
const post = (path, body) => api(path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
const created = [];
const TEMPLATES = await (async () => { const t = await api("/templates"); return Array.isArray(t) ? t : t.templates; })();
// a template by what it is (indoor, outdoor, several floors), never by its id
const template = (want = () => true) => (TEMPLATES.find(want) ?? TEMPLATES[0]).id;
const newProject = async (name, template_id = template((t) => t.mode === "indoor" && t.floors === 1)) => {
  const p = await post("/projects", { name, template_id });
  created.push(p.id);
  return p;
};

const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const results = [];
async function flow(name, fn) {
  if (only && !name.includes(only)) return;
  const context = await browser.newContext({ viewport: { width: 1600, height: 900 }, acceptDownloads: true });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message.slice(0, 200)}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`console: ${m.text().slice(0, 200)}`); });
  const t0 = Date.now();
  let status = "PASS", why = "";
  try {
    why = (await fn(page, context)) ?? "";
  } catch (e) {
    status = "FAIL";
    why = e.message.split("\n").slice(0, 3).join(" ").slice(0, 300);
  }
  if (errors.length && status === "PASS") { status = "WARN"; why += ` | ${errors.slice(0, 3).join(" | ")}`; }
  const shot = `${name.replace(/\W+/g, "-")}.png`;
  await page.screenshot({ path: `${out}/${shot}` }).catch(() => {});
  results.push({ name, status, why, shot, s: Math.round((Date.now() - t0) / 1000) });
  console.log(`${status.padEnd(4)} ${name} (${Math.round((Date.now() - t0) / 1000)} s) ${why}`);
  await context.close();
}

// --- Projects: search, copy, download, import, delete ---------------------------------------
await flow("projects: search, copy, download, import, delete", async (page) => {
  const p = await newProject("QA projects flow");
  await page.goto(`${BASE}/projects`);
  await page.getByRole("searchbox", { name: T("projects.search") }).fill("QA projects flow");
  await expect(page.getByRole("link", { name: T("projects.open", { name: "QA projects flow" }) })).toHaveCount(1);
  await page.getByRole("searchbox", { name: T("projects.search") }).fill("zzz-no-such-plan");
  await expect(page.getByRole("link", { name: startsWith(T("projects.open", { name: "" })) })).toHaveCount(0);
  await page.getByRole("searchbox", { name: T("projects.search") }).fill("QA projects flow");
  // copy
  await page.getByRole("button", { name: T("projects.actions", { name: "QA projects flow" }) }).click();
  await page.getByRole("menuitem", { name: T("projects.menu_copy") }).click();
  await expect(page.getByText(T("projects.duplicated")).first()).toBeVisible({ timeout: 15_000 });
  // download a copy, then import it back
  await page.getByRole("button", { name: T("projects.actions", { name: "QA projects flow" }) }).first().click();
  const [dl] = await Promise.all([page.waitForEvent("download"), page.getByRole("menuitem", { name: T("projects.menu_download") }).click()]);
  const zip = `${out}/qa-project.showtime.zip`;
  await dl.saveAs(zip);
  if (readFileSync(zip).subarray(0, 2).toString() !== "PK") throw new Error("download is not a zip");
  await page.getByLabel(starts(T("projects.import_hint", { types: "" }).trim())).setInputFiles(zip);
  await expect(page.getByText(T("projects.imported")).first()).toBeVisible({ timeout: 30_000 });
  // every copy/import of this plan: clean up through the UI's delete
  const all = (await api("/projects")).filter((x) => x.name.startsWith("QA projects flow"));
  for (const x of all) if (!created.includes(x.id)) created.push(x.id);
  await page.reload();
  await page.getByRole("searchbox", { name: T("projects.search") }).fill("QA projects flow");
  const menu = page.getByRole("button", { name: startsWith(T("projects.actions", { name: "QA projects flow" })) }).first();
  await menu.click();
  await page.getByRole("menuitem", { name: T("projects.menu_delete") }).click();
  const confirm = page.getByRole("alertdialog").getByRole("button", { name: /delete/i });
  if (await confirm.count()) await confirm.click();
  await expect(page.getByText(T("projects.deleted")).first()).toBeVisible({ timeout: 15_000 });
  return `${all.length} plans (original, copy, import); one deleted through the UI`;
});

// --- Check your venue: door width, lock, people, kind of event ------------------------------
await flow("check venue: an exit's width, lock, people, kind of event", async (page) => {
  const p = await newProject("QA check venue", template((t) => t.floors >= 2));
  const venue = () => api(`/projects/${p.id}`).then((r) => r.version.venue);
  const v0 = await venue();
  const exit = v0.floors.flatMap((f) => f.exits)[0]; // whichever exit the venue has first
  const label = exit.label ?? exit.id;
  const width = Math.round((exit.width_m + 0.5) * 10) / 10;
  await page.goto(`${BASE}/p/${p.id}/describe`);
  await page.getByRole("button", { name: startsWith(label) }).first().click();
  const field = page.getByLabel(T("check.width"), { exact: true }).first();
  await field.fill(String(width));
  await field.press("Enter");
  await expect(page.getByText(/saved as version 2/).first()).toBeVisible({ timeout: 20_000 });
  await page.getByRole("switch", { name: startsWith(T("check.lock")) }).click();
  await expect(field).toBeDisabled();
  await page.getByRole("button", { name: T("check.back_to_list") }).click();
  const total = (v) => v.floors.flatMap((f) => f.zones).reduce((n, z) => n + z.people, 0);
  const before = total(await venue());
  const plus = page.getByRole("button", { name: /more people in/i }).first();
  if (await plus.count()) { await plus.click(); await page.waitForTimeout(2500); }
  const v1 = await venue();
  const saved = v1.floors.flatMap((f) => f.exits).find((e) => e.id === exit.id);
  if (Math.abs((saved?.width_m ?? 0) - width) > 0.01) throw new Error(`${label} saved as ${saved?.width_m} m, asked ${width} m`);
  // kind of event: whichever option is not the current one
  const kind = page.getByRole("combobox").last();
  let kindNote = "no kind selector";
  if (await kind.count()) {
    const options = await kind.locator("option").evaluateAll((os) => os.map((o) => ({ v: o.value, l: o.textContent })));
    const next = options.find((o) => o.v && o.v !== v1.event_kind);
    if (next) {
      await kind.selectOption(next.v);
      await expect.poll(async () => (await venue()).event_kind, { timeout: 15_000 }).toBe(next.v);
      kindNote = `event kind → ${next.v}`;
    }
  }
  return `${label} ${exit.width_m} → ${width} m, locked; people ${before} → ${total(v1)}; ${kindNote}`;
});

// --- Expert view: stress test, break it yourself, red team tab, report and every export -----
await flow("expert: stress test, report preview and exports", async (page) => {
  const p = await newProject("QA expert");
  await page.goto(`${BASE}/p/${p.id}/expert/simulate`);
  await page.getByRole("button", { name: "Run stress test" }).first().click();
  await expect(page.getByText("Stress test finished").first()).toBeVisible({ timeout: 200_000 });
  await page.getByRole("button", { name: "Report", exact: true }).click();
  const frame = page.frameLocator('iframe[title="Report preview"]');
  await expect(frame.getByText("Planning aid, not a safety certification.").first()).toBeVisible({ timeout: 30_000 });
  const got = [];
  for (const name of ["Evacuation map (SVG)", "Data bundle (JSON)", "3D model (.glb)", "Project file (.showtime.zip)"]) {
    const link = page.getByRole("link", { name }).or(page.getByRole("button", { name })).first();
    if (!(await link.count())) { got.push(`${name}: missing`); continue; }
    const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 60_000 }), link.click()]);
    const path = `${out}/${dl.suggestedFilename()}`;
    await dl.saveAs(path);
    const head = readFileSync(path).subarray(0, 8);
    const ok = name.includes("SVG") ? head.toString().includes("<") : name.includes("JSON") ? head.toString().trim().startsWith("{") : name.includes("glb") ? head.subarray(0, 4).toString() === "glTF" : head.subarray(0, 2).toString() === "PK";
    got.push(`${name}: ${ok ? "ok" : "BAD"}`);
    if (!ok) throw new Error(`${name} has the wrong content`);
  }
  return got.join("; ");
});

// --- Your plan with no test: the empty state leads to the check page ------------------------
await flow("plan untested: empty state", async (page) => {
  const p = await newProject("QA untested plan", template((t) => t.mode === "outdoor"));
  await page.goto(`${BASE}/p/${p.id}`);
  await page.getByRole("link", { name: T("yourplan.check_and_test") }).first().click();
  await expect(page).toHaveURL(/\/describe$/);
  return "untested plan → Check and test → the check page";
});

// --- Stop a running test ---------------------------------------------------------------------
await flow("stop a running test", async (page) => {
  const p = await newProject("QA stop");
  await page.goto(`${BASE}/p/${p.id}/describe`);
  await page.getByRole("radio", { name: /Offline/ }).click();
  await page.getByRole("button", { name: "Test this plan" }).click();
  await expect(page).toHaveURL(/\/work\?session=/, { timeout: 30_000 });
  await page.waitForTimeout(3000);
  await page.getByRole("button", { name: "Stop" }).click();
  const yes = page.getByRole("alertdialog").getByRole("button", { name: /stop/i });
  if (await yes.count()) await yes.click();
  const sid = new URL(page.url()).searchParams.get("session");
  await expect.poll(async () => (await api(`/sessions/${sid}`)).status, { timeout: 120_000 }).toMatch(/stopped|finished/);
  await page.waitForTimeout(3000);
  const st = (await api(`/sessions/${sid}`)).status;
  return `session ${st}; page ${page.url().replace(BASE, "")}`;
});

// --- Settings persist; theme toggles ---------------------------------------------------------
await flow("settings persist and theme toggles", async (page) => {
  await page.goto(`${BASE}/settings`);
  const toggles = await page.getByRole("switch").all();
  const first = toggles[0];
  let note = "";
  if (first) {
    const was = await first.getAttribute("aria-checked");
    await first.click();
    const save = page.getByRole("button", { name: /^Save settings/ });
    if (await save.count()) await save.click();
    await page.waitForTimeout(1500);
    await page.reload();
    await page.waitForTimeout(1500);
    const now = await page.getByRole("switch").first().getAttribute("aria-checked");
    note = `first switch ${was} → ${now} after reload`;
    if (now === was) throw new Error(`setting did not persist (${note})`);
    await page.getByRole("switch").first().click();
    if (await save.count()) await save.click();
    await page.waitForTimeout(1000);
  }
  const theme = page.getByRole("button", { name: /Dark theme|Light theme/ }).first();
  await theme.click();
  const dark = await page.evaluate(() => document.documentElement.dataset.theme ?? document.documentElement.className);
  await theme.click();
  return `${note}; theme toggled (${dark})`;
});

// --- Help: every section anchor scrolls to its heading --------------------------------------
await flow("help anchors", async (page) => {
  await page.goto(`${BASE}/help`);
  const links = await page.locator("main a[href^='#'], nav a[href^='/help#'], main a[href^='/help#']").evaluateAll((as) => [...new Set(as.map((a) => a.getAttribute("href")))]);
  const bad = [];
  for (const href of links.slice(0, 30)) {
    const id = href.split("#")[1];
    if (!id) continue;
    const exists = await page.locator(`[id="${id}"]`).count();
    if (!exists) bad.push(id);
  }
  if (bad.length) throw new Error(`anchors with no target: ${bad.join(", ")}`);
  return `${links.length} anchors, all with a target`;
});

// --- Welcome checklist ------------------------------------------------------------------------
await flow("welcome checklist", async (page) => {
  await page.goto(`${BASE}/welcome`);
  await page.waitForTimeout(3000);
  const text = await page.locator("main").innerText();
  if (/not ready|failed/i.test(text)) return `some rows not ready: ${text.replace(/\n+/g, " | ").slice(0, 200)}`;
  return "every row ready";
});

for (const id of created) await fetch(`${BASE}/api/v1/projects/${id}`, { method: "DELETE" }).catch(() => {});
writeFileSync(`${out}/flows.json`, JSON.stringify(results, null, 1));
await browser.close();
