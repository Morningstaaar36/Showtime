// Screenshot helper: node e2e/shoot.mjs <outdir> <path> [<path> ...]  (paths relative to http://127.0.0.1:5173)
// Options via env: THEME=dark, WAIT=ms, W=1600, H=900
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const [outDir, ...paths] = process.argv.slice(2);
mkdirSync(outDir, { recursive: true });
const browser = await chromium.launch({ args: ["--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist"] });
const ctx = await browser.newContext({
  viewport: { width: Number(process.env.W ?? 1600), height: Number(process.env.H ?? 900) },
  colorScheme: process.env.THEME === "dark" ? "dark" : "light",
  deviceScaleFactor: 1,
});
const page = await ctx.newPage();
const errors = [];
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 300)); });
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message.slice(0, 200)}\n${(e.stack ?? "").split("\n").slice(1, 9).join("\n")}`));
for (const p of paths) {
  const [path, action] = p.split("#");
  await page.goto(`http://127.0.0.1:5173${path}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(Number(process.env.WAIT ?? 2500));
  if (action) {
    for (const step of action.split(";")) {
      const [kind, arg] = step.split("=");
      if (kind === "click") await page.getByText(arg, { exact: false }).first().click();
      if (kind === "key") await page.keyboard.press(arg);
      if (kind === "wait") await page.waitForTimeout(Number(arg));
    }
  }
  const name = (path.replaceAll("/", "_") || "root") + (action ? `_${action.replace(/[^a-z0-9]+/gi, "-").slice(0, 40)}` : "");
  await page.screenshot({ path: `${outDir}/${name}.png` });
  console.log(`shot ${outDir}/${name}.png`);
}
if (errors.length) console.log("CONSOLE ERRORS:\n" + [...new Set(errors)].slice(0, 15).join("\n"));
await browser.close();
