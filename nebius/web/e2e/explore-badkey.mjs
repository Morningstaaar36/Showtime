// Step 7, flow 8: a bad model key. Run against an API started with an invalid key (BASE): the
// badge, describing a venue, the Expert view banner, and a Standard test. Screenshots to <outdir>.
// Usage: BASE=http://127.0.0.1:5174 node e2e/explore-badkey.mjs <outdir>
import { chromium } from "@playwright/test";
const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [out] = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
const say = async (what, loc) => console.log(what, (await loc.innerText().catch(() => "(none)")).replace(/\n+/g, " | ").slice(0, 400));
// the provider badge is on Settings (and in Expert view), not in the organizer header
await page.goto(`${BASE}/settings`);
await page.waitForTimeout(2500);
await page.getByRole("button", { name: /^AI:/ }).first().click();
await page.waitForTimeout(800);
await page.screenshot({ path: `${out}/flow8-badkey-badge.png` });
await say("badge:", page.getByRole("dialog").first());
await page.keyboard.press("Escape");
await page.goto(`${BASE}/`);
// describe a venue
await page.getByRole("button", { name: /^Describe it/ }).first().click();
await page.getByRole("textbox").first().fill("A school hall 30 by 20 m with 400 pupils and two doors on the south side.");
await page.getByRole("button", { name: "Just draw my venue" }).click();
const toastText = await page.waitForFunction(() => [...document.querySelectorAll("[data-sonner-toast]")].map((e) => e.textContent).join(" || ") || null, undefined, { timeout: 120_000, polling: 100 }).then((h) => h.jsonValue()).catch(() => "no toast");
console.log("describe toast:", toastText);
await page.screenshot({ path: `${out}/flow8-badkey-describe.png` });
await say("describe:", page.getByRole("alert").first());
console.log("toasts:", JSON.stringify(await page.evaluate(() => [...document.querySelectorAll("[data-sonner-toast]")].map((e) => e.textContent))));
// a template project: Expert view banner, then a Standard test
const pid = (await (await fetch(`${BASE}/api/v1/projects`, { method: "POST", headers: { "content-type": "application/json", "X-Showtime": "1" }, body: JSON.stringify({ template_id: "school_wing", name: "Bad key check" }) })).json()).id;
await page.goto(`${BASE}/p/${pid}/expert`);
await page.waitForTimeout(3000);
await page.screenshot({ path: `${out}/flow8-badkey-expert.png` });
await say("banner:", page.getByRole("status").filter({ hasText: /AI/ }).first());
await page.goto(`${BASE}/p/${pid}/describe`);
await page.getByText("More options", { exact: true }).click(); // the test depth is under More options
await page.getByRole("radio", { name: /Standard/ }).click();
await page.getByRole("button", { name: "Test this plan" }).click();
await page.waitForURL(/\/work\?session=|\/p\/p_[^/]+\?session=/, { timeout: 60_000 }).catch(() => {});
await page.waitForURL(/\/p\/p_[^/]+\?session=/, { timeout: 600_000 }).catch(() => console.log("did not reach the plan"));
await page.waitForTimeout(3000);
await page.screenshot({ path: `${out}/flow8-badkey-plan.png` });
await say("plan:", page.locator("main"));
await browser.close();
