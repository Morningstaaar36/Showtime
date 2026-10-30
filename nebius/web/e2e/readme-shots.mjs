// The README's screenshots, headless, from what the running app holds: the Home page, the AI team,
// the map, a tested sample, and a real case built through the app (chosen by its case title; no
// project id is written here). Usage (app running):
//   node e2e/readme-shots.mjs <outdir> "<real case title>" [live]
// With "live", it waits for that case's test to be running and shoots "AI at work" while it runs.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [out, caseTitle, mode] = process.argv.slice(2);
if (!out || !caseTitle) throw new Error('usage: node e2e/readme-shots.mjs <outdir> "<case title>" [live]');
mkdirSync(out, { recursive: true });
const api = async (p) => (await fetch(`${BASE}/api/v1${p}`)).json();
const sessionsOf = async (pid) => { const r = await api(`/projects/${pid}/sessions`); return Array.isArray(r) ? r : r.sessions ?? []; };

const browser = await chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist"] });
async function shot(name, path, { theme = "light", wait = 3500, act } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: theme, deviceScaleFactor: 1 });
  await ctx.addInitScript((t) => { try { localStorage.setItem("showtime.prefs.v1", JSON.stringify({ state: { theme: t }, version: 0 })); } catch { /* storage off */ } }, theme);
  const page = await ctx.newPage();
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" }).catch(() => {});
  await page.waitForTimeout(wait);
  if (act) await act(page).catch((e) => console.log(`  (${name}: ${e.message.split("\n")[0]})`));
  await page.screenshot({ path: `${out}/${name}.png` });
  console.log(`shot ${name}`);
  await ctx.close();
}

const findCase = async () => (await api("/real_cases")).find((c) => c.title === caseTitle);

if (mode === "live") {
  // wait for the case's project and a running test, then shoot AI at work twice as it fills
  let pid = null, sid = null;
  for (let i = 0; i < 360 && !sid; i++) {
    pid = (await findCase())?.project_id ?? null;
    if (pid) sid = (await sessionsOf(pid)).find((s) => s.status === "running")?.id ?? null;
    if (!sid) await new Promise((r) => setTimeout(r, 5000));
  }
  if (!sid) throw new Error("no running test found");
  await new Promise((r) => setTimeout(r, 45_000));
  await shot("bailey-work", `/p/${pid}/work?session=${sid}&live=1`, { wait: 6000 });
  await browser.close();
  process.exit(0);
}

const row = await findCase();
if (!row?.project_id) throw new Error(`no project for “${caseTitle}”`);
const pid = row.project_id;
const done = (await sessionsOf(pid)).filter((s) => s.status === "finished");
const sid = done.at(-1)?.id;
const sample = (await api("/projects")).find((p) => p.sample && p.floors > 1) ?? (await api("/projects")).find((p) => p.sample);
const sampleSid = sample ? (await sessionsOf(sample.id)).find((s) => s.status === "finished")?.id : null;

await shot("home", "/");
await shot("team", "/team");
await shot("map", "/new/place", { wait: 5000 });
if (sample && sampleSid) {
  await shot("sample-plan", `/p/${sample.id}?session=${sampleSid}`);
  await shot("sample-replay", `/p/${sample.id}/expert/analysis?session=${sampleSid}&tab=scenarios`);
}
await shot("bailey-check", `/p/${pid}/describe`, {
  act: async (page) => {
    await page.getByText("How the AI designed this").first().scrollIntoViewIfNeeded();
    await page.getByText("How the AI designed this").first().evaluate((el) => el.scrollIntoView({ block: "start" }));
    await page.waitForTimeout(800);
  },
});
await shot("bailey-3d", `/p/${pid}/describe`, {
  act: async (page) => {
    const floors = page.getByRole("radiogroup", { name: "Floors to show" }).first();
    await floors.getByRole("radio", { name: /^All floors/ }).click();
    await page.waitForTimeout(2500);
  },
});
await shot("bailey-3d-dark", `/p/${pid}/describe`, {
  theme: "dark",
  act: async (page) => {
    const floors = page.getByRole("radiogroup", { name: "Floors to show" }).first();
    await floors.getByRole("radio").nth(2).click();
    await page.waitForTimeout(2500);
  },
});
if (sid) await shot("bailey-plan", `/p/${pid}?session=${sid}`, { wait: 5000 });
await browser.close();
