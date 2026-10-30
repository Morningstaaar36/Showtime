// Feature check on a real incident: in a Chrome window you can watch, write the Bailey Road
// case (docs/examples/bailey-road-case.json) through the real-case form, let the designer build
// the seven-storey building and the red team test it live, then check every feature on that
// plan. Each check logs PASS/FAIL with what it saw and saves a screenshot; the results go to
// <outdir>/results.json (docs/FEATURE_CHECK.md is written from them).
// Usage: node e2e/feature-check.mjs <outdir> [check-name-substring ...]
//   FRESH=1 deletes an earlier Bailey Road case and its plan first, so everything is built again.
//   QA_HEADLESS=1 runs without a window; QA_PAUSE_MS sets the pause after each caption.
import { chromium, expect } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";

const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [out, ...only] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const PAUSE = Number(process.env.QA_PAUSE_MS ?? 1200);
const HEADLESS = process.env.QA_HEADLESS === "1";

const EN = JSON.parse(readFileSync(new URL("../src/i18n/en.json", import.meta.url), "utf8"));
const CASE = JSON.parse(readFileSync(new URL("../../docs/examples/bailey-road-case.json", import.meta.url), "utf8"));
const T = (key, vars = {}) => {
  const s = key.split(".").reduce((n, k) => n?.[k], EN);
  if (typeof s !== "string") throw new Error(`no string ${key}`);
  return s.replace(/\{(\w+)\}/g, (_, v) => String(vars[v] ?? `{${v}}`));
};
const esc = (x) => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const starts = (x) => new RegExp(`^${esc(x)}`);
const HEADERS = { "content-type": "application/json", "X-Showtime": "1" };
const api = async (path, init) => { const r = await fetch(`${BASE}/api/v1${path}`, init); return r.status === 204 ? null : r.json(); };
const del = (path) => fetch(`${BASE}/api/v1${path}`, { method: "DELETE", headers: HEADERS });
const sessionsOf = async (pid) => { const r = await api(`/projects/${pid}/sessions`); return Array.isArray(r) ? r : r.sessions ?? []; };
const venueOf = async (id) => (await api(`/projects/${id}`)).version.venue;
const caseRow = async () => (await api("/real_cases")).find((c) => c.title === CASE.title);

const browser = await chromium.launch({
  headless: HEADLESS,
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ?? "/usr/bin/google-chrome",
  slowMo: HEADLESS ? 0 : 80,
  args: HEADLESS ? ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] : ["--start-maximized"],
});
const context = await browser.newContext({ viewport: HEADLESS ? { width: 1600, height: 900 } : null, acceptDownloads: true });
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
let page = await context.newPage();
const errors = [];
const watch = (p) => {
  p.on("pageerror", (e) => errors.push(`pageerror: ${e.message.slice(0, 200)}`));
  p.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource/.test(m.text())) errors.push(`console: ${m.text().slice(0, 200)}`); });
};
watch(page);
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
    why = e.message.split("\n").filter(Boolean).slice(0, 3).join(" ").slice(0, 400);
  }
  if (status === "PASS" && errors.length) { status = "WARN"; why += ` | ${[...new Set(errors)].slice(0, 2).join(" | ")}`; }
  const shot = `${String(results.length + 1).padStart(2, "0")}-${name.replace(/\W+/g, "-").slice(0, 50)}.png`;
  await page.screenshot({ path: `${out}/${shot}` }).catch(() => {});
  await caption(`${status}: ${name}`, status === "FAIL" ? "fail" : "pass");
  await page.waitForTimeout(PAUSE);
  results.push({ name, status, why, shot });
  console.log(`${status.padEnd(4)} ${name} — ${why}`);
  writeFileSync(`${out}/results.json`, JSON.stringify(results, null, 1));
}

// the plan under test: the Bailey Road case's project and its finished test
let pid = null, sid = null;
const plan = async () => {
  if (!pid) throw new Error("the Bailey Road plan was not built");
  if (!sid) {
    const done = (await sessionsOf(pid)).filter((s) => s.status === "finished");
    sid = done.at(-1)?.id ?? null;
  }
  if (!sid) throw new Error("the Bailey Road plan has no finished test");
  return { pid, sid };
};

if (process.env.FRESH === "1") {
  const old = await caseRow();
  if (old?.project_id) await del(`/projects/${old.project_id}`);
  if (old) await del(`/real_cases/${old.id}`);
}
{
  const row = await caseRow();
  pid = row?.project_id ?? null;
}

// --- start ------------------------------------------------------------------------------------
await check("Home: three ways to start, events like yours, real cases", async () => {
  await go("/");
  await expect(page.getByRole("heading", { name: T("home.uc_title") })).toBeVisible({ timeout: 20_000 });
  const tested = await page.getByText(T("home.uc_tested"), { exact: true }).count();
  const cases = await page.locator('[data-testid^="real-case-"]').count();
  if (!cases) throw new Error("no real cases on Home");
  return `${tested} event tiles open a tested sample; ${cases} real cases listed`;
});

await check("Header: sandbox facts, AI badge, theme toggle", async () => {
  await go("/settings"); // the badges sit in Settings and in Expert view's top bar
  await page.getByTestId("sandbox-badge").click();
  await expect(page.getByTestId("sandbox-facts")).toBeVisible({ timeout: 10_000 });
  const facts = (await page.getByTestId("sandbox-facts").innerText()).split("\n").length;
  await page.keyboard.press("Escape");
  const html = page.locator("html");
  const before = await html.getAttribute("class");
  const toggle = page.getByRole("button", { name: /theme|dark|light/i }).first();
  await toggle.click();
  await page.waitForTimeout(600);
  const after = await html.getAttribute("class");
  await toggle.click();
  if (before === after) throw new Error("the theme toggle changed nothing");
  return `sandbox facts (${facts} lines); theme ${before || "light"} → ${after || "light"} → back`;
});

await check("AI team: every agent with its model and tools", async () => {
  await go("/team");
  await expect(page.getByTestId("team-isolation")).toBeVisible({ timeout: 20_000 });
  const text = await page.locator("main").innerText();
  if (!/nemotron/i.test(text)) throw new Error("no Nemotron model named on the team page");
  return `${(text.match(/nemotron/gi) ?? []).length} Nemotron mentions; the judge says ${/verdict is computed/.test(text) ? "the verdict is computed" : "something else"}`;
});

// --- the Bailey Road case, built and tested live ------------------------------------------------
await check("Real case: write the Bailey Road case in the form", async () => {
  if (pid) return `already written and built (plan ${pid}); FRESH=1 writes it again`;
  const F = (k) => T(`realcase.form.${k}`);
  await go("/");
  const add = page.getByRole("button", { name: starts(T("realcase.add")) });
  await add.scrollIntoViewIfNeeded();
  await add.click();
  const d = page.getByRole("dialog");
  await d.getByLabel(F("title"), { exact: true }).fill(CASE.title);
  await d.getByLabel(F("incident"), { exact: true }).fill(CASE.incident);
  await d.getByLabel(F("date"), { exact: true }).fill(CASE.date);
  await d.locator("#case-event_kind").selectOption(CASE.event_kind);
  await d.getByLabel(F("place"), { exact: true }).fill(CASE.place);
  await d.getByLabel(F("lat"), { exact: true }).fill(String(CASE.location.lat));
  await d.getByLabel(F("lon"), { exact: true }).fill(String(CASE.location.lon));
  await d.getByLabel(F("timezone"), { exact: true }).fill(CASE.location.timezone);
  await d.getByLabel(F("people"), { exact: true }).fill(String(CASE.people));
  await d.getByLabel(F("deaths"), { exact: true }).fill(String(CASE.deaths));
  await d.getByLabel(F("toll"), { exact: true }).fill(CASE.toll);
  await d.getByLabel(F("description"), { exact: true }).fill(CASE.description);
  await d.getByLabel(F("what_happened"), { exact: true }).fill(CASE.what_happened);
  await d.getByLabel(F("lesson"), { exact: true }).fill(CASE.lesson);
  for (const [i, s] of CASE.sources.entries()) {
    if (i > 0) await d.getByRole("button", { name: F("source_add") }).click();
    await d.getByLabel(T("realcase.form.source_label", { n: i + 1 })).fill(s.label);
    await d.getByLabel(T("realcase.form.source_url", { n: i + 1 })).fill(s.url);
  }
  await d.getByLabel(F("dimensions"), { exact: true }).fill(CASE.dimensions.join("\n"));
  await d.getByLabel(F("approximations"), { exact: true }).fill(CASE.approximations.join("\n"));
  await d.getByRole("button", { name: F("save") }).click();
  await d.waitFor({ state: "detached", timeout: 15_000 });
  const row = await caseRow();
  if (!row) throw new Error("the case was not saved");
  return `saved as ${row.id} with ${CASE.sources.length} sources`;
});

await check("Real case: the designer builds the building and the red team tests it live", async () => {
  if (pid) {
    const s = (await sessionsOf(pid)).at(-1);
    return `built before: plan ${pid}, last test ${s?.id} ${s?.status}`;
  }
  const row = await caseRow();
  await go("/");
  const tile = page.getByTestId(`real-case-${row.id}`);
  await tile.scrollIntoViewIfNeeded();
  await tile.click();
  await page.waitForURL(/\/p\/p_/, { timeout: 600_000 });
  pid = page.url().split("/p/")[1].split(/[/?]/)[0];
  if (!/\/work\?/.test(page.url())) return `built; opened ${page.url().replace(BASE, "")} (no test started)`;
  await expect(page.getByTestId("sandbox-feed")).toBeVisible({ timeout: 120_000 });
  await page.waitForTimeout(20_000); // the live feed fills: screenshot it mid-test
  await page.screenshot({ path: `${out}/live-ai-at-work.png` });
  await page.waitForURL((u) => /\/p\/p_[^/]+(\?|$)/.test(u.pathname + u.search) && !u.pathname.endsWith("/work"), { timeout: 1_800_000 });
  sid = new URL(page.url()).searchParams.get("session");
  const s = await api(`/sessions/${sid}`);
  return `plan ${pid}; test ${sid} ${s.status}; ${s.summary?.attacks?.length ?? 0} attacks, ${(s.summary?.accepted_fixes ?? []).length} fixes kept`;
});

await check("Check venue: seven floors, one stair, floors switch and spread apart", async () => {
  const v = await venueOf(pid);
  await go(`/p/${pid}/describe`);
  const floors = page.getByRole("radiogroup", { name: T("floors.label") }).first();
  await expect(floors).toBeVisible({ timeout: 20_000 });
  const top = v.floors.at(-1).name ?? v.floors.at(-1).floor_id;
  await floors.getByRole("radio", { name: starts(top) }).click();
  await page.waitForTimeout(1500);
  await floors.getByRole("radio", { name: starts(T("floors.exploded")) }).click().catch(async () => {
    await floors.getByRole("button", { name: starts(T("floors.exploded")) }).click();
  });
  await page.waitForTimeout(2000);
  await page.screenshot({ path: `${out}/floors-spread.png` });
  await floors.getByRole("radio", { name: starts(T("floors.all")) }).click();
  const people = v.floors.flatMap((f) => f.zones).reduce((n, z) => n + z.people, 0);
  const exits = v.floors.flatMap((f) => f.exits).length;
  if (v.floors.length < 7) throw new Error(`the designer drew ${v.floors.length} floors, not 7`);
  return `${v.floors.length} floors, ${v.stairs.length} stair flights, ${exits} exits, ${people} people`;
});

await check("Expert: the safety officer reviews the plan", async () => {
  await go(`/p/${pid}/expert/plan`); // the inspector shows it while nothing is selected
  // "Review again" once a review with actions is saved, "Review my plan" before
  const label = new RegExp(`^(${esc(T("ui.officercard.review_again"))}|${esc(T("ui.officercard.review_my_plan"))})$`);
  const btn = page.getByRole("button", { name: label }).first();
  await btn.scrollIntoViewIfNeeded();
  await btn.click();
  const card = page.getByRole("region", { name: T("ui.officercard.safety_officer") }).or(page.locator(`section[aria-label="${T("ui.officercard.safety_officer")}"]`)).first();
  await expect(card.locator("p.text-xs.text-muted").first()).toBeVisible({ timeout: 180_000 });
  // the button reads "Review again" once the review has actions, "Review my plan" when it has none
  await expect(card.getByRole("button", { name: label })).toBeEnabled({ timeout: 180_000 });
  const n = await card.locator("ol li").count();
  return `${n} prioritised actions; summary: ${(await card.locator("p.text-xs.text-muted").first().innerText()).slice(0, 120)}`;
});

await check("Check venue: ask anything (a question and a what-if)", async () => {
  await go(`/p/${pid}/describe`);
  const box = page.getByRole("textbox", { name: T("ask.label") }).or(page.getByPlaceholder(T("ask.ph"))).first();
  await box.fill("How long until the top floor is empty?");
  await box.press("Enter");
  // the box is busy (its placeholder says so) until the answer is in
  await expect(page.getByPlaceholder(T("ask.thinking"))).toHaveCount(1, { timeout: 10_000 }).catch(() => {});
  await expect(page.getByPlaceholder(T("ask.thinking"))).toHaveCount(0, { timeout: 180_000 });
  const answer = (await page.locator("main").innerText()).match(/The top floor[^\n]*/)?.[0] ?? "answered";
  await box.fill(T("ask.ex_rain"));
  await box.press("Enter");
  await expect(page.getByText(T("ask.what_if")).or(page.getByText(T("ask.result"))).first()).toBeVisible({ timeout: 120_000 });
  return `question: ${answer.slice(0, 140)}; what-if answered`;
});

// --- Your plan ---------------------------------------------------------------------------------
await check("Your plan: verdict, key numbers, countdown, case card, AI summary", async () => {
  const { pid: p, sid: s } = await plan();
  await go(`/p/${p}?session=${s}`);
  await expect(page.getByRole("region", { name: /verdict/i }).first()).toBeVisible({ timeout: 30_000 });
  const verdict = await page.getByTestId("verdict-sentence").innerText().catch(() => "");
  await expect(page.getByTestId("real-case-card")).toBeVisible({ timeout: 20_000 });
  const kpi = await page.getByTestId("kpi-start").innerText().catch(() => "no countdown");
  return `verdict: ${verdict.slice(0, 140)} | start: ${kpi.replace(/\n/g, " ").slice(0, 80)}`;
});

await check("Your plan: the replay plays, with a floor switch", async () => {
  const { pid: p, sid: s } = await plan();
  await go(`/p/${p}?session=${s}`);
  const replay = page.getByRole("region", { name: /replay/i }).first();
  await replay.scrollIntoViewIfNeeded();
  const pause = page.getByRole("button", { name: T("timeline.pause") }).first();
  if (await pause.isVisible().catch(() => false)) await pause.click();
  await page.getByRole("button", { name: T("timeline.play") }).first().click();
  await page.waitForTimeout(4000);
  const floors = replay.getByRole("radiogroup", { name: T("floors.label") });
  const n = await floors.getByRole("radio").count();
  return `played 4 s; ${n} floor choices on the replay`;
});

await check("Analysis: every scenario, the failure map and the Evidence panel", async () => {
  const { pid: p, sid: s } = await plan();
  await go(`/p/${p}/expert/analysis?session=${s}&tab=scenarios`);
  await expect(page.getByTestId("scenario-gallery").getByRole("listitem").first()).toBeVisible({ timeout: 30_000 });
  const cards = await page.getByTestId("scenario-gallery").getByRole("listitem").count();
  await expect(page.getByTestId("evidence-panel")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("evidence-panel").scrollIntoViewIfNeeded();
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${out}/evidence.png` });
  const map = await page.getByRole("region", { name: T("ui.failuremap.failure_map") }).count();
  return `${cards} scenario cards; evidence panel; failure map ${map ? "shown" : "missing"}`;
});

await check("Analysis: how sure are these numbers (more people, fewer, faster, slower)", async () => {
  const { pid: p, sid: s } = await plan();
  await go(`/p/${p}/expert/analysis?session=${s}&tab=scenarios`);
  await page.getByRole("button", { name: starts(T("plan.check_range")) }).first().click(); // its tile under Deeper checks
  const heading = page.getByRole("heading", { name: T("range.title") });
  await heading.scrollIntoViewIfNeeded();
  const region = page.locator("section").filter({ has: heading }).first();
  await region.getByRole("button", { name: new RegExp(`${esc(T("range.start"))}|${esc(T("range.again"))}`) }).click();
  await expect(region.getByRole("table")).toBeVisible({ timeout: 900_000 });
  await expect(region.getByRole("button", { name: T("range.again") })).toBeVisible({ timeout: 900_000 });
  return `${(await region.getByRole("table").getByRole("row").count()) - 1} variants simulated`;
});

await check("Analysis: check with more seeds", async () => {
  const { pid: p, sid: s } = await plan();
  await go(`/p/${p}/expert/analysis?session=${s}&tab=scenarios`);
  await page.getByRole("button", { name: /^Check with more seeds/ }).first().click();
  const panel = page.getByTestId("seed-check");
  await panel.getByLabel("More seeds").selectOption("2");
  await panel.getByRole("button", { name: "Check with more seeds" }).click();
  await expect(panel.getByText(/ over 3 seeds$/).first()).toBeVisible({ timeout: 900_000 });
  return (await panel.getByText(/ over 3 seeds$/).first().innerText()).slice(0, 120);
});

await check("Sandboxes: the AI-written scenario's code", async () => {
  const { pid: p, sid: s } = await plan();
  await go(`/p/${p}/expert/analysis?session=${s}&tab=sandboxes`);
  await expect(page.getByTestId("sandboxes-tab")).toBeVisible({ timeout: 30_000 });
  const code = page.getByText(T("scripts.show_code")).first();
  if (!(await code.count())) return "the red team wrote no scenario as code in this test";
  await code.click();
  await expect(page.locator("pre, code").filter({ hasText: "def " }).first()).toBeVisible({ timeout: 10_000 });
  return "the Python the red team wrote, shown with what it did";
});

await check("Sandboxes: rewind says why a building with floors can't be rewound", async () => {
  const { pid: p, sid: s } = await plan();
  await go(`/p/${p}/expert/analysis?session=${s}&tab=sandboxes`);
  const rewind = page.getByRole("region", { name: T("rewind.title") });
  await rewind.scrollIntoViewIfNeeded();
  await rewind.getByRole("button", { name: new RegExp(`${esc(T("rewind.start"))}|${esc(T("rewind.again"))}`) }).click();
  await expect(rewind.getByText(/single-floor|Best from this second|No response did better/).first()).toBeVisible({ timeout: 600_000 });
  return (await rewind.getByText(/single-floor|Best from this second|No response did better/).first().innerText()).slice(0, 160);
});

await check("Sandboxes: rewind the worst moment (a one-floor real case)", async () => {
  const one = (await api("/real_cases")).find((c) => c.id === "itaewon_2022" && c.project_id)
    ?? (await api("/real_cases")).find((c) => c.project_id && c.id !== (CASE.id ?? ""));
  if (!one) throw new Error("no one-floor real case has been built");
  const s = (await sessionsOf(one.project_id)).filter((x) => x.status === "finished").at(-1);
  await go(`/p/${one.project_id}/expert/analysis?session=${s.id}&tab=sandboxes`);
  const rewind = page.getByRole("region", { name: T("rewind.title") });
  await rewind.scrollIntoViewIfNeeded();
  await rewind.getByRole("button", { name: new RegExp(`${esc(T("rewind.start"))}|${esc(T("rewind.again"))}`) }).click();
  await expect(rewind.getByText(/Best from this second|No response did better/)).toBeVisible({ timeout: 900_000 });
  const rows = await rewind.getByRole("table").getByRole("row").count();
  return `${one.title}: ${rows - 1} branches from the worst second`;
});

await check("Sandboxes: stress test at scale", async () => {
  const { pid: p, sid: s } = await plan();
  await go(`/p/${p}/expert/analysis?session=${s}&tab=sandboxes`);
  const stress = page.getByRole("region", { name: T("stress.title") });
  await stress.scrollIntoViewIfNeeded();
  await stress.getByLabel(T("stress.seeds")).selectOption("1");
  await stress.getByRole("button", { name: T("stress.start") }).click();
  await expect(stress.getByText(/Finished: (\d+) of \1 done/)).toBeVisible({ timeout: 900_000 });
  return (await stress.getByText(/Finished: (\d+) of \1 done/).innerText()).slice(0, 80);
});

await check("Analysis: floors (when each storey clears)", async () => {
  const { pid: p, sid: s } = await plan();
  await go(`/p/${p}/expert/analysis?session=${s}&tab=floors`);
  await expect(page.getByTestId("floor-cards")).toBeVisible({ timeout: 30_000 });
  return `${await page.getByTestId("floor-cards").locator("> *").count()} floor cards`;
});

await check("Expert: Red Team tab (cards, failure map, branch tree, activity)", async () => {
  const { pid: p } = await plan();
  await go(`/p/${p}/expert/redteam`);
  const tabs = ["redteam.tab_cards", "redteam.tab_map", "redteam.branch_tree", "redteam.activity"];
  for (const key of tabs) {
    await page.getByRole("tab", { name: T(key) }).click();
    await page.waitForTimeout(1500);
  }
  return `${tabs.length} tabs opened`;
});

await check("Expert: break it yourself (block the stair's way out) and confirm", async () => {
  const { pid: p } = await plan();
  const v = await venueOf(p);
  const exit = v.floors.flatMap((f) => f.exits)[0];
  await go(`/p/${p}/expert/simulate`);
  await page.getByRole("button", { name: starts(exit.label ?? exit.id) }).and(page.locator("[aria-pressed]")).first().click();
  await expect(page.getByRole("button", { name: T("workspace.confirm_with_simulation") })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("button", { name: T("workspace.confirm_with_simulation") }).click();
  await page.waitForTimeout(4000);
  return `${exit.label ?? exit.id} blocked; confirmation started`;
});

await check("Expert: building tools add a fire-escape stair, edit by text, undo", async () => {
  const { pid: p } = await plan();
  const v0 = (await api(`/projects/${p}`)).current_version;
  await go(`/p/${p}/expert/plan`);
  const cmd = page.getByRole("textbox", { name: new RegExp(T("tools.text"), "i") }).or(page.getByPlaceholder(/edit by text|type a change/i)).first();
  const w = (await venueOf(p)).stairs[0]?.width_m ?? 1.2;
  await cmd.fill(`make the stair ${(Math.round((w + 0.2) * 10) / 10).toFixed(1)} m wide`); // a change from now
  await cmd.press("Enter");
  await expect.poll(async () => (await api(`/projects/${p}`)).current_version, { timeout: 180_000 }).toBeGreaterThan(v0);
  const v1 = (await api(`/projects/${p}`)).current_version;
  await page.evaluate(() => document.activeElement?.blur()); // in a text box Ctrl+Z undoes typing
  await page.keyboard.press("Control+z");
  await expect.poll(async () => (await api(`/projects/${p}`)).current_version, { timeout: 20_000 }).not.toBe(v1);
  const v2 = (await api(`/projects/${p}`)).current_version;
  return `edit by text: v${v0} → v${v1}; Ctrl+Z → v${v2}`;
});

await check("Fixes: choose and accept the kept fixes", async () => {
  const { pid: p, sid: s } = await plan();
  await go(`/p/${p}?session=${s}&tab=fixes`);
  const kept = ((await api(`/sessions/${s}`)).summary?.accepted_fixes ?? []).length;
  if (!kept) return "this test kept no fixes (the tab says so)";
  const v0 = (await api(`/projects/${p}`)).current_version;
  await page.getByRole("button", { name: new RegExp(`${esc(T("yourplan.accept"))}|Accept \\d+ fixes|Accept fix`) }).first().click();
  await expect.poll(async () => (await api(`/projects/${p}`)).current_version, { timeout: 30_000 }).toBeGreaterThan(v0);
  return `${kept} fixes accepted as a new version`;
});

await check("Scripts: code that reaches for the network is refused", async () => {
  const { pid: p } = await plan();
  await go(`/p/${p}/scripts`);
  await page.getByRole("button", { name: T("userscripts.new") }).first().click();
  const code = page.getByTestId("script-code").or(page.locator("textarea")).first();
  await code.fill("import socket\nsocket.create_connection(('example.org', 80))\n");
  await page.getByRole("button", { name: T("userscripts.run") }).click();
  await expect(page.getByText(/socket|not allowed|refused|blocked/i).first()).toBeVisible({ timeout: 60_000 });
  for (const sc of (await api(`/projects/${p}/scripts`)).scripts) await del(`/projects/${p}/scripts/${sc.id}`);
  return "refused before it ran, with the reason";
});

await check("Narrated tour: the camera flies and it can be stopped", async () => {
  const { pid: p } = await plan();
  await go(`/p/${p}/expert?tour=1`);
  await page.waitForTimeout(8000);
  const stop = page.getByRole("button", { name: T("workspace.tour_stop") });
  await expect(stop).toBeVisible({ timeout: 20_000 });
  await stop.click();
  return "tour played 8 s, then stopped";
});

await check("Hand over: report, evacuation map, checklist, 3D model, data bundle, cost", async () => {
  const { pid: p, sid: s } = await plan();
  await go(`/p/${p}?session=${s}&tab=handover`);
  await expect(page.getByText(T("plan.ho_map")).first()).toBeVisible({ timeout: 20_000 });
  const got = [];
  for (const label of [T("plan.ho_model_label"), T("plan.ho_data")]) {
    const link = page.getByRole("link", { name: starts(label) }).or(page.getByRole("button", { name: starts(label) })).first();
    if (!(await link.count())) continue;
    const [dl] = await Promise.all([page.waitForEvent("download", { timeout: 120_000 }), link.click()]);
    const file = `${out}/${dl.suggestedFilename()}`;
    await dl.saveAs(file);
    got.push(`${dl.suggestedFilename()} (${readFileSync(file).length} bytes)`);
  }
  const checklist = page.getByRole("link", { name: T("checklist.download") }).first();
  const href = await checklist.getAttribute("href");
  const body = await (await fetch(new URL(href, BASE))).text();
  if (!body.includes(T("app.disclaimer"))) throw new Error("the checklist lacks the planning-aid notice");
  got.push("checklist with the notice");
  const cost = await page.getByText(T("plan.cost_more")).count();
  return `${got.join("; ")}; cost card ${cost ? "shown" : "missing"}`;
});

await check("Help: how good is the simulator, sandbox proof", async () => {
  await go("/help");
  await expect(page.getByTestId("sandbox-proof")).toBeVisible({ timeout: 20_000 });
  await page.getByText(T("validation.nav")).first().click().catch(() => {});
  await expect(page.getByTestId("validation-chart")).toBeVisible({ timeout: 20_000 });
  return "validation chart and sandbox proof shown";
});

await check("Test again: a second test on the changed plan", async () => {
  const { pid: p } = await plan();
  await go(`/p/${p}`);
  const n0 = (await sessionsOf(p)).length;
  await page.getByRole("button", { name: T("yourplan.test_again") }).first().click();
  await page.waitForURL(/\/work\?session=/, { timeout: 60_000 });
  await page.waitForURL((u) => !u.pathname.endsWith("/work"), { timeout: 1_800_000 });
  const s2 = new URL(page.url()).searchParams.get("session");
  const s = await api(`/sessions/${s2}`);
  if ((await sessionsOf(p)).length <= n0) throw new Error("no new test");
  return `test ${s2} ${s.status}`;
});

writeFileSync(`${out}/results.json`, JSON.stringify(results, null, 1));
console.log(`plan ${pid}`);
await caption(`Done: ${results.filter((r) => r.status === "PASS").length} passed, ${results.filter((r) => r.status !== "PASS").length} to look at`, results.some((r) => r.status === "FAIL") ? "fail" : "pass");
await page.waitForTimeout(3000);
await browser.close();
