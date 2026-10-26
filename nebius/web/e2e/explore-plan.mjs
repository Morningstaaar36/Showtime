// Step 7, flows 3–7 on a tested plan, in Chrome: Show the code, Rewind, Stress test at scale (live
// counters), the handover downloads, a real case, and the AI team page. Screenshots to <outdir>.
// Usage: node e2e/explore-plan.mjs <outdir> <project id> <session id>
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";
const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [out, pid, sid] = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const ctx = await browser.newContext({ viewport: { width: 1600, height: 900 }, acceptDownloads: true });
const page = await ctx.newPage();
const text = async (loc) => (await loc.innerText()).replace(/\n+/g, " | ").slice(0, 500);
if (process.env.FROM !== "handover") {
await page.goto(`${BASE}/p/${pid}?session=${sid}&tab=sandboxes`);
const tab = page.getByTestId("sandboxes-tab");
await tab.waitFor();
await tab.getByText("Show the code").first().click();
await page.waitForTimeout(800);
await page.screenshot({ path: `${out}/flow3-show-code.png` });
console.log("code:", (await tab.locator("pre, code").first().innerText()).slice(0, 300).replace(/\n/g, " ⏎ "));
// flow 4: rewind, then the stress test
const rewind = page.getByRole("region", { name: "Rewind the worst moment" });
await rewind.getByRole("button", { name: "Rewind the worst moment" }).click();
await rewind.getByText(/Best from this second|No response did better/).waitFor({ timeout: 400_000 });
await rewind.scrollIntoViewIfNeeded();
await page.screenshot({ path: `${out}/flow4-rewind.png` });
console.log("rewind:", await text(rewind));
const stress = page.getByRole("region", { name: "Stress test at scale" });
await stress.getByRole("button", { name: "Run stress test at scale" }).click();
await stress.getByText(/\d+ of \d+ done/).first().waitFor({ timeout: 60_000 });
await page.screenshot({ path: `${out}/flow4-stress-live.png` });
console.log("stress live:", await text(stress));
await stress.getByText(/Finished: (\d+) of \1 done/).waitFor({ timeout: 900_000 });
await page.screenshot({ path: `${out}/flow4-stress-done.png` });
console.log("stress done:", await text(stress));
}
// flow 7: hand over
await page.goto(`${BASE}/p/${pid}?session=${sid}`);
await page.getByRole("tab", { name: /^Hand over/ }).click();
await page.waitForTimeout(1500);
await page.screenshot({ path: `${out}/flow7-handover.png`, fullPage: true });
for (const name of ["Download checklist", "Download report"]) {
  // the hand-over tiles link to the printable pages (they open in a new tab)
  const href = await page.getByRole("link", { name }).first().getAttribute("href");
  const body = await (await fetch(new URL(href, BASE))).text();
  console.log(name, "→", href, body.length, "bytes; disclaimer:", body.includes("Planning aid, not a safety certification"));
}
// flow 5: a real case; flow 6: the AI team page
await page.goto(`${BASE}/`);
await page.getByTestId("real-case-itaewon_2022").dblclick();
await page.getByTestId("real-case-card").waitFor({ timeout: 60_000 });
await page.waitForTimeout(2000);
await page.screenshot({ path: `${out}/flow5-itaewon.png` });
console.log("case card:", await text(page.getByTestId("real-case-card")));
await page.goto(`${BASE}/team`);
await page.waitForTimeout(2000);
await page.screenshot({ path: `${out}/flow6-team.png`, fullPage: true });
console.log("team isolation:", await text(page.getByTestId("team-isolation")));
await browser.close();
