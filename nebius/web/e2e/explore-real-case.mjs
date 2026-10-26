// A real case on a fresh install: double-click its tile, watch the designer build it once, and
// see the case card. Usage: node e2e/explore-real-case.mjs <outdir> [case id]
import { chromium } from "@playwright/test";
const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [out, id = "itaewon_2022"] = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
const opens = [];
page.on("request", (r) => { if (r.method() === "POST" && r.url().includes("/real_cases/")) opens.push(r.url()); });
const t0 = Date.now();
await page.goto(`${BASE}/`);
const tile = page.getByTestId(`real-case-${id}`);
await tile.scrollIntoViewIfNeeded();
await tile.dblclick();
await page.waitForURL(/\/p\/p_/, { timeout: 300_000 });
console.log(`opened in ${((Date.now() - t0) / 1000).toFixed(0)} s:`, page.url(), "| open requests:", opens.length);
await page.getByTestId("real-case-card").waitFor({ timeout: 120_000 }).catch(() => console.log("no case card"));
await page.waitForTimeout(2000);
await page.screenshot({ path: `${out}/clean-clone-real-case.png` });
console.log("card:", (await page.getByTestId("real-case-card").innerText().catch(() => "")).replace(/\n+/g, " | ").slice(0, 300));
const cases = await (await fetch(`${BASE}/api/v1/real_cases`)).json();
console.log("projects per case:", JSON.stringify(cases.map((c) => [c.id, c.project_id])));
await browser.close();
