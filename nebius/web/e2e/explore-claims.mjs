// Check demo-script claims on screen: the Evidence panel's web-search slot and Help's
// validation line. Usage: node e2e/explore-claims.mjs <outdir> <project id> <session id>
import { chromium } from "@playwright/test";
const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [out, pid, sid] = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
await page.goto(`${BASE}/p/${pid}?session=${sid}&tab=scenarios`);
const ev = page.getByTestId("evidence-panel");
await ev.waitFor({ timeout: 60_000 });
await ev.scrollIntoViewIfNeeded();
await page.screenshot({ path: `${out}/claims-evidence.png` });
const text = (await ev.innerText()).replace(/\n+/g, " | ");
console.log("evidence mentions web search:", /web search/i.test(text), "|", text.match(/[^|]*web search[^|]*/i)?.[0] ?? "");
await page.goto(`${BASE}/help`);
await page.getByText("How good is the simulator?").first().click().catch(() => {});
await page.waitForTimeout(1500);
const help = (await page.locator("main").innerText()).replace(/\n+/g, " | ");
console.log("validation:", help.match(/[^|]*within [^|]*real crowd[^|]*/i)?.[0] ?? help.match(/[^|]*simulator's flow[^|]*/i)?.[0] ?? "(not found)");
await page.screenshot({ path: `${out}/claims-validation.png` });
await browser.close();
