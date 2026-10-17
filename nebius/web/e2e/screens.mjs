// Screenshot every screen for the self-review and the README.
// Usage: node e2e/screens.mjs <outdir>   (app running at BASE, default http://127.0.0.1:5173)
// Optional projects: "Hospital…" (a building drawn on the map with several floors) and "Untested…"
// (no test yet) give the multi-storey and empty-plan shots; without them those shots are skipped.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const outDir = process.argv[2] ?? "../docs/screenshots";
const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
mkdirSync(outDir, { recursive: true });

const projects = await (await fetch(`${BASE}/api/v1/projects`)).json();
// samples first: test and evaluation projects can share words with them ("alley")
const byName = (re) => (projects.find((p) => p.sample && re.test(p.name)) ?? projects.find((p) => re.test(p.name)))?.id;
const alley = byName(/alley/i);
const hall = byName(/summit|two-floor/i);
const festival = byName(/festival|wellington/i);
const hospital = byName(/^hospital/i); // a multi-storey building drawn on the map (see below)
const untested = byName(/^untested/i);

/** [name, path, theme, steps] — steps: "wait=ms" | "click=text" | "key=K" */
const SHOTS = [
  ["welcome", "/welcome", "light"],
  ["projects", "/", "light"],
  ["projects-dark", "/", "dark"],
  ["settings", "/settings", "light"],
  ["help", "/help", "light"],
  ["not-found", "/nope", "light"],
  ["plan", `/p/${hall}/expert/plan`, "light"],
  ["plan-dark", `/p/${hall}/expert/plan`, "dark"],
  ["wind", `/p/${festival}/expert/plan`, "light"],
  ["simulate", `/p/${alley}/expert/simulate`, "light", ["wait=1500", "key=Space", "wait=6000", "key=Space"]],
  ["simulate-dark", `/p/${alley}/expert/simulate`, "dark", ["wait=1500", "key=Space", "wait=6000", "key=Space"]],
  ["redteam", `/p/${hall}/expert/redteam`, "light"],
  ["redteam-dark", `/p/${alley}/expert/redteam`, "dark"],
  ["branch-tree", `/p/${hall}/expert/redteam`, "light", ["click=Branch tree", "wait=1500"]],
  ["report", `/p/${festival}/expert/report`, "light", ["wait=3000"]],
  ["missing-project", "/p/p_doesnotexist/plan", "light"],
  // the three simple screens (S-07), light and dark, filled and empty
  ["home", "/", "light"],
  ["home-dark", "/", "dark"],
  ["check", `/p/${hall}/describe`, "light"],
  ["check-dark", `/p/${hall}/describe`, "dark"],
  ["plan-simple", `/p/${alley}`, "light", ["wait=3000"]],
  ["plan-simple-dark", `/p/${alley}`, "dark", ["wait=3000"]],
  ["plan-untested", `/p/${untested}`, "light"],
  ["map", "/new/place", "light"],
  ["help-verdict", "/help#verdict", "light"],
  // buildings: drawing tools and a multi-storey venue
  ["building-tools", `/p/${hall}/expert/plan`, "light", ["key=o", "wait=800"]],
  ["hospital-check", `/p/${hospital}/describe`, "light", ["wait=2000"]],
  ["hospital-spread", `/p/${hospital}/describe`, "light", ["click=Spread apart", "wait=2500"]],
  ["hospital-check-dark", `/p/${hospital}/describe`, "dark", ["wait=2000"]],
];

const browser = await chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist"] });
const errors = [];
for (const [name, path, theme, steps = []] of SHOTS) {
  if (path.includes("/undefined/")) { console.log(`skip ${name}: sample project not found`); continue; }
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 }, colorScheme: theme, deviceScaleFactor: 1 });
  await ctx.addInitScript((t) => { try { localStorage.setItem("showtime.prefs.v1", JSON.stringify({ theme: t })); } catch { /* ignore */ } }, theme);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => errors.push(`${name}: ${e.message.slice(0, 200)}`));
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${name}: ${m.text().slice(0, 200)}`); });
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(3500);
  for (const step of steps) {
    const [kind, arg] = step.split("=");
    if (kind === "wait") await page.waitForTimeout(Number(arg));
    if (kind === "key") await page.keyboard.press(arg);
    if (kind === "click") await page.getByText(arg, { exact: false }).first().click();
  }
  await page.screenshot({ path: `${outDir}/${name}.png` });
  console.log(`shot ${name}`);
  await ctx.close();
}
await browser.close();
if (errors.length) console.log("CONSOLE ERRORS:\n" + [...new Set(errors)].slice(0, 20).join("\n"));
