// Screenshot every screen for the self-review and the README.
// Usage: node e2e/screens.mjs <outdir>   (app running at BASE, default http://127.0.0.1:5173)
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const outDir = process.argv[2] ?? "../docs/screenshots";
const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
mkdirSync(outDir, { recursive: true });

const projects = await (await fetch(`${BASE}/api/v1/projects`)).json();
const byName = (re) => projects.find((p) => re.test(p.name))?.id;
const alley = byName(/alley/i);
const hall = byName(/summit|two-floor/i);
const festival = byName(/festival|wellington/i);

/** [name, path, theme, steps] — steps: "wait=ms" | "click=text" | "key=K" */
const SHOTS = [
  ["welcome", "/welcome", "light"],
  ["projects", "/", "light"],
  ["projects-dark", "/", "dark"],
  ["settings", "/settings", "light"],
  ["help", "/help", "light"],
  ["not-found", "/nope", "light"],
  ["plan", `/p/${hall}/plan`, "light"],
  ["plan-dark", `/p/${hall}/plan`, "dark"],
  ["wind", `/p/${festival}/plan`, "light"],
  ["simulate", `/p/${alley}/simulate`, "light", ["wait=1500", "key=Space", "wait=6000", "key=Space"]],
  ["simulate-dark", `/p/${alley}/simulate`, "dark", ["wait=1500", "key=Space", "wait=6000", "key=Space"]],
  ["redteam", `/p/${hall}/redteam`, "light"],
  ["redteam-dark", `/p/${alley}/redteam`, "dark"],
  ["branch-tree", `/p/${hall}/redteam`, "light", ["click=Branch tree", "wait=1500"]],
  ["report", `/p/${festival}/report`, "light", ["wait=3000"]],
  ["missing-project", "/p/p_doesnotexist/plan", "light"],
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
