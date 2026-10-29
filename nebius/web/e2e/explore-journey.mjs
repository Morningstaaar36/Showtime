// Step 7, flow 2: the guided journey from a template, in Chrome. Start a test, watch AI at work
// (sandbox feed, tool calls), then the plan (Evidence panel, Sandboxes tab). Screenshots to <outdir>.
// Usage: node e2e/explore-journey.mjs <outdir> [template button name] [mode]
import { chromium } from "@playwright/test";
const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [out, template = "School wing", mode = "Standard"] = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
const t0 = Date.now();
const at = () => `${((Date.now() - t0) / 1000).toFixed(0)} s`;
await page.goto(`${BASE}/projects`);
await page.getByRole("button", { name: new RegExp(`^${template}`) }).first().click();
await page.getByRole("button", { name: "Create project" }).click();
await page.waitForURL(/\/describe$/);
const pid = page.url().split("/p/")[1].split("/")[0];
console.log("project", pid);
await page.getByText("More options", { exact: true }).click(); // the test depth lives there
await page.getByRole("radio", { name: new RegExp(mode) }).click();
await page.getByRole("button", { name: "Test this plan" }).click();
await page.waitForURL(/\/work\?session=/, { timeout: 60_000 });
console.log(at(), "AI at work", page.url().split("session=")[1]);
const feed = page.getByTestId("sandbox-feed");
await feed.getByTestId("sandbox-row").first().waitFor({ timeout: 300_000 });
// let a few runs land, then the shot of the live feed
await page.locator('[data-testid="sandbox-row"][data-state="finished"]').nth(1).waitFor({ timeout: 400_000 }).catch(() => {});
await feed.scrollIntoViewIfNeeded();
await page.mouse.wheel(0, 250);
await page.waitForTimeout(500);
await page.screenshot({ path: `${out}/work-sandbox-feed-${mode.toLowerCase()}.png` });
console.log(at(), "feed:", (await feed.innerText()).replace(/\n+/g, " | ").slice(0, 400));
const tools = page.getByTestId("tool-calls");
if (await tools.count()) console.log(at(), "tools:", (await tools.innerText()).replace(/\n+/g, " | ").slice(0, 400));
await page.waitForURL(/\/p\/p_[^/]+\?session=/, { timeout: 900_000 });
await page.waitForTimeout(3000);
console.log(at(), "Your plan");
await page.screenshot({ path: `${out}/plan-overview.png` });
console.log("verdict:", (await page.getByRole("region", { name: "Verdict" }).innerText()).replace(/\n+/g, " | ").slice(0, 300));
await page.getByRole("link", { name: "More analysis in Expert view" }).click(); // scenarios and sandboxes live there
await page.getByRole("tab", { name: /^Scenarios/ }).click();
await page.waitForTimeout(1500);
const ev = page.getByTestId("evidence-panel");
if (await ev.count()) { await ev.scrollIntoViewIfNeeded(); await page.screenshot({ path: `${out}/plan-evidence.png` }); console.log("evidence:", (await ev.innerText()).replace(/\n+/g, " | ").slice(0, 500)); }
else console.log("evidence panel: not found");
await page.getByRole("tab", { name: /^Sandboxes/ }).click();
await page.waitForTimeout(1500);
await page.screenshot({ path: `${out}/plan-sandboxes.png`, fullPage: true });
console.log("sandboxes tab:", (await page.getByTestId("sandboxes-tab").innerText()).replace(/\n+/g, " | ").slice(0, 600));
await browser.close();
