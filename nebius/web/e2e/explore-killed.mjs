// Step 7, flow 8: a sandbox stopped mid-run. Start an Offline test (no model), kill the running
// simulation container from outside, and see what AI at work and the plan say.
// Usage: node e2e/explore-killed.mjs <outdir>
import { chromium } from "@playwright/test";
import { execSync } from "node:child_process";
const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [out] = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
const pid = (await (await fetch(`${BASE}/api/v1/projects`, { method: "POST", headers: { "content-type": "application/json", "X-Showtime": "1" }, body: JSON.stringify({ template_id: "school_wing", name: "Explore killed sandbox" }) })).json()).id;
await page.goto(`${BASE}/p/${pid}/describe`);
await page.getByText("More options", { exact: true }).click(); // the test depth is under More options
await page.getByRole("radio", { name: /Offline/ }).click();
await page.getByRole("button", { name: "Test this plan" }).click();
await page.waitForURL(/\/work\?session=/, { timeout: 60_000 });
// wait for a sim container, then kill it
let killed = "";
for (let i = 0; i < 120 && !killed; i++) {
  const ids = execSync("docker ps -q --filter ancestor=showtime-sim:latest", { env: { ...process.env, DOCKER_CONTEXT: "default" } }).toString().trim();
  if (ids) { killed = ids.split("\n")[0]; execSync(`docker kill ${killed}`, { env: { ...process.env, DOCKER_CONTEXT: "default" } }); }
  else await page.waitForTimeout(500);
}
console.log("killed container", killed);
const feed = page.getByTestId("sandbox-feed");
await feed.getByText(/The first sandbox stopped/).waitFor({ timeout: 300_000 }).catch(() => console.log("no restart note appeared"));
await feed.scrollIntoViewIfNeeded().catch(() => {});
await page.screenshot({ path: `${out}/flow8-killed-sandbox.png` });
console.log("feed:", (await feed.innerText().catch(() => "")).replace(/\n+/g, " | ").slice(0, 700));
await page.waitForURL(/\/p\/p_[^/]+\?session=/, { timeout: 600_000 }).catch(() => console.log("did not reach the plan"));
await page.waitForTimeout(3000);
await page.screenshot({ path: `${out}/flow8-killed-plan.png` });
console.log("plan:", (await page.locator("main").innerText()).replace(/\n+/g, " | ").slice(0, 500));
await fetch(`${BASE}/api/v1/projects/${pid}`, { method: "DELETE", headers: { "X-Showtime": "1" } });
await browser.close();
