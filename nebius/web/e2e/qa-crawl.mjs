// QA crawler: visit every screen for several kinds of project, record console errors, page
// errors, failed requests, crash screens, raw i18n keys and sideways overflow; then click every
// safe button and tab on the page and record what each click breaks. Screenshots + report.json
// go to <outdir>. Usage: node e2e/qa-crawl.mjs <outdir> [only-route-substring]
import { chromium } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";

const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [out, only] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const api = async (path, init) => (await fetch(`${BASE}/api/v1${path}`, init)).json();

// projects of every kind, chosen by what they are (never by name): with and without a finished
// test, one floor and several, indoor and outdoor, a real case, and a fresh untested one
const projects = await api("/projects");
const sessionOf = async (id) => {
  const r = await api(`/projects/${id}/sessions`);
  const list = Array.isArray(r) ? r : r.sessions ?? [];
  return list.find((s) => s.status === "finished")?.id ?? null;
};
const facts = [];
for (const p of projects.slice(0, 80)) {
  const v = (await api(`/projects/${p.id}`)).version?.venue;
  if (!v) continue;
  facts.push({ p, sid: await sessionOf(p.id), floors: v.floors.length, mode: v.mode, realCase: !!v.extensions?.real_case, sample: !!p.sample });
}
const wants = [
  (f) => f.sid && f.mode === "outdoor",
  (f) => f.sid && f.mode === "indoor" && f.floors === 1,
  (f) => f.sid && f.floors >= 2,
  (f) => f.sid && f.floors >= 3,
  (f) => f.realCase,
  (f) => f.sample,
  (f) => !f.sid,
];
const chosen = [];
for (const want of wants) {
  const f = facts.find((x) => want(x) && !chosen.includes(x.p));
  if (f) chosen.push(f.p);
}
const templates = await api("/templates");
const tpl = (Array.isArray(templates) ? templates : templates.templates)[0];
const fresh = await api("/projects", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ name: "QA untested", template_id: tpl.id }) });
chosen.push(fresh);

const routes = ["/", "/projects", "/new/place", "/welcome", "/settings", "/help", "/team", "/nope-404"];
for (const p of chosen) {
  const sid = await sessionOf(p.id);
  const q = sid ? `?session=${sid}` : "";
  routes.push(`/p/${p.id}${q}`);
  if (sid) for (const tab of ["replay", "scenarios", "sandboxes", "fixes", "floors", "handover"]) routes.push(`/p/${p.id}${q}&tab=${tab}`);
  routes.push(`/p/${p.id}/describe`);
  if (sid) routes.push(`/p/${p.id}/work${q}`);
  for (const m of ["plan", "simulate", "redteam", "report"]) routes.push(`/p/${p.id}/expert/${m}`);
  routes.push(`/p/${p.id}/scripts`);
}

// never click these: they change data, start long work, or leave the app
const UNSAFE = /delete|remove|stop|test this plan|test again|run|start|accept|apply|reset|upload|import|rewind|stress|more seeds|plan it|just draw|build|create|save|sign|lock|undo|redo|block|confirm|send|ask|review my plan|use this venue|download|export|print|duplicate|new project|new script|try a sample|open the map|choose|hide|tour|showtime lights|break|demo|add|record|copy|share|log ?out|clear|refresh/i;

const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const report = [];
let n = 0;
// QA_CHUNK=k/n crawls the k-th of n equal parts (each fits a time limit)
const [k, nChunks] = (process.env.QA_CHUNK ?? "1/1").split("/").map(Number);
const per = Math.ceil(routes.length / nChunks);
const mine = routes.slice((k - 1) * per, k * per);
console.log(`chunk ${k}/${nChunks}: ${mine.length} of ${routes.length} screens`);
for (const route of mine) {
  if (only && !route.includes(only)) continue;
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  const issues = [];
  page.on("console", (m) => { if (m.type() === "error") issues.push(`console: ${m.text().slice(0, 220)}`); });
  page.on("pageerror", (e) => issues.push(`pageerror: ${e.message.slice(0, 220)}`));
  page.on("response", (r) => {
    const u = r.url();
    if (r.status() >= 400 && u.includes("/api/") && !u.includes("p_doesnotexist")) issues.push(`http ${r.status()}: ${u.replace(BASE, "").slice(0, 160)}`);
  });
  const t0 = Date.now();
  try {
    await page.goto(`${BASE}${route}`, { waitUntil: "domcontentloaded", timeout: 60_000 });
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
    await page.waitForTimeout(1500);
  } catch (e) { issues.push(`goto: ${e.message.slice(0, 160)}`); }
  const body = await page.locator("body").innerText().catch(() => "");
  if (/something went wrong|unexpected error|cannot read properties|undefined is not/i.test(body)) issues.push("crash text on screen");
  const keys = [...new Set(body.match(/\b[a-z][a-z0-9]*(?:_[a-z0-9]+)*\.[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b/g) ?? [])].filter((k) => !/\.(json|zip|glb|svg|png|md|py|bin|html|csv|txt)$/.test(k) && !/^(e|i)\.g\./.test(k));
  if (keys.length) issues.push(`raw keys? ${keys.slice(0, 6).join(", ")}`);
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  if (wide > 1) issues.push(`sideways overflow ${wide}px`);
  const shot = `${String(++n).padStart(3, "0")}.png`;
  await page.screenshot({ path: `${out}/${shot}` }).catch(() => {});

  // click pass
  const clicks = [];
  const handles = await page.locator("main button:visible, main [role=tab]:visible, main summary:visible, header button:visible").all();
  const seen = new Set();
  for (const h of handles.slice(0, 30)) {
    const name = ((await h.getAttribute("aria-label").catch(() => null)) ?? (await h.innerText().catch(() => ""))).trim().replace(/\s+/g, " ").slice(0, 60);
    if (!name || seen.has(name) || UNSAFE.test(name) || (await h.isDisabled().catch(() => true))) continue;
    seen.add(name);
    const before = issues.length;
    const url = page.url();
    try {
      await h.click({ timeout: 2000 });
      await page.waitForTimeout(400);
    } catch { continue; }
    const after = await page.locator("body").innerText().catch(() => "");
    if (/something went wrong|cannot read properties/i.test(after)) issues.push(`crash after clicking "${name}"`);
    if (issues.length > before) clicks.push(`"${name}" → ${issues.slice(before).join(" ; ")}`);
    await page.keyboard.press("Escape").catch(() => {});
    if (page.url() !== url) await page.goto(url, { waitUntil: "domcontentloaded" }).catch(() => {});
  }
  const row = { route, shot, ms: Date.now() - t0, issues: [...new Set(issues)], clicks, clicked: seen.size };
  report.push(row);
  console.log(`${row.issues.length ? "ISSUES" : "ok    "} ${route} (${(row.ms / 1000).toFixed(0)} s, ${row.clicked} clicks)${row.issues.length ? "\n        " + row.issues.slice(0, 6).join("\n        ") : ""}`);
  await page.close();
}
await fetch(`${BASE}/api/v1/projects/${fresh.id}`, { method: "DELETE" });
writeFileSync(`${out}/report-${k}of${nChunks}.json`, JSON.stringify(report, null, 1));
await browser.close();
