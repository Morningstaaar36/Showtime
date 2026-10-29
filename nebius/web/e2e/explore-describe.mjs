// Step 7, flow 1: describe a venue in one sentence (Home › Describe it › Just draw my venue), for
// several kinds of venue; screenshot Check your venue and print its levels, exits and headcounts.
// Usage: node e2e/explore-describe.mjs <outdir> <name> "<sentence>" [<name> "<sentence>" ...]
import { chromium } from "@playwright/test";
const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [out, ...pairs] = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
for (let i = 0; i < pairs.length; i += 2) {
  const [name, sentence] = [pairs[i], pairs[i + 1]];
  const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
  const t0 = Date.now();
  await page.goto(`${BASE}/`);
  await page.getByRole("button", { name: /^Describe it/ }).first().click();
  await page.getByRole("textbox").first().fill(sentence);
  await page.getByRole("button", { name: "Just draw my venue" }).click();
  try {
    await page.waitForURL(/\/p\/p_[^/]+\/describe/, { timeout: 300_000 });
  } catch {
    await page.screenshot({ path: `${out}/describe-${name}-error.png` });
    console.log(name, "FAILED:", (await page.locator("main").innerText()).slice(0, 400).replace(/\n+/g, " | "));
    await page.close();
    continue;
  }
  await page.waitForTimeout(4000);
  const pid = page.url().split("/p/")[1].split("/")[0];
  const v = (await (await fetch(`${BASE}/api/v1/projects/${pid}`)).json()).version.venue;
  const floors = v.floors.map((f) => `${f.name ?? f.floor_id}: ${f.zones.reduce((n, z) => n + z.people, 0)} people, exits [${f.exits.map((e) => `${e.label ?? e.id} ${e.width_m} m`).join(", ")}]`);
  console.log(`${name} (${((Date.now() - t0) / 1000).toFixed(0)} s) ${pid} "${v.name}" · ${v.mode} · ${v.floors.length} level(s), ${(v.stairs ?? []).length} stairs`);
  for (const f of floors) console.log("   ", f);
  // the provider badge is on Settings, no longer in this header
  await page.goto(`${BASE}/settings`);
  console.log("    badge:", (await page.getByRole("button", { name: /^AI:/ }).first().textContent())?.trim());
  await page.goto(`${BASE}/p/${pid}/describe`);
  await page.screenshot({ path: `${out}/describe-${name}.png` });
  await page.close();
}
await browser.close();
