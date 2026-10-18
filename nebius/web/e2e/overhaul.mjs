// Screenshots for the visual overhaul review.
// Usage: node e2e/overhaul.mjs <outdir> "name|path|theme|WxH|steps" ...
//   theme: light | dark; size: 1440x900 | 390x844; steps: "wait=ms;click=text;tab=Name;key=K;scroll=px;full"
// App at BASE (default http://127.0.0.1:5181).
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const BASE = process.env.BASE ?? "http://127.0.0.1:5181";
const [outDir, ...specs] = process.argv.slice(2);
mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist"] });
const errors = [];
for (const spec of specs) {
  const [name, path, theme = "light", size = "1440x900", steps = ""] = spec.split("|");
  const [w, h] = size.split("x").map(Number);
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: theme === "dark" ? "dark" : "light", deviceScaleFactor: 1 });
  await ctx.addInitScript((th) => localStorage.setItem("showtime.prefs.v1", JSON.stringify({ theme: th })), theme);
  const page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error") errors.push(`${name}: ${m.text().slice(0, 300)}`); });
  page.on("pageerror", (e) => errors.push(`${name}: pageerror ${e.message.slice(0, 300)}`));
  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" }).catch(() => {});
  await page.waitForTimeout(Number(process.env.WAIT ?? 2500));
  let full = false;
  for (const step of steps.split(";").filter(Boolean)) {
    const [kind, arg] = step.split("=");
    try {
      if (kind === "wait") await page.waitForTimeout(Number(arg));
      if (kind === "click") await page.getByText(arg, { exact: false }).first().click({ timeout: 5000 });
      if (kind === "tab") await page.getByRole("tab", { name: arg }).first().click({ timeout: 5000 });
      if (kind === "role") { const [r, n] = arg.split(":"); await page.getByRole(r, { name: n }).first().click({ timeout: 5000 }); }
      if (kind === "key") await page.keyboard.press(arg);
      if (kind === "scroll") await page.mouse.wheel(0, Number(arg));
      if (kind === "full") full = true;
    } catch (e) { errors.push(`${name}: step ${step} failed: ${String(e).slice(0, 160)}`); }
  }
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${outDir}/${name}.png`, fullPage: full });
  const sw = await page.evaluate(() => document.documentElement.scrollWidth);
  console.log(`shot ${outDir}/${name}.png${sw > w ? `  SIDEWAYS SCROLL ${sw}>${w}` : ""}`);
  await ctx.close();
}
if (errors.length) console.log("ERRORS:\n" + [...new Set(errors)].slice(0, 30).join("\n"));
await browser.close();
