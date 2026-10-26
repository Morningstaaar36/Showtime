// The 3-minute demo of docs/DEMO.md as one take, in order, with a screenshot per beat.
// Usage: node e2e/explore-demo.mjs <outdir>
import { chromium } from "@playwright/test";
const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [out] = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
const T0 = Date.now();
const mark = (beat, ok, note = "") => console.log(`${ok ? "PASS" : "FAIL"} ${beat} (${((Date.now() - T0) / 1000).toFixed(0)} s) ${note}`);
const text = async (loc) => (await loc.innerText().catch(() => "")).replace(/\n+/g, " | ");

// Before the demo: Projects › New project › School wing › "Spring open day" › Standard › Test this plan
await page.goto(`${BASE}/projects`);
await page.getByRole("button", { name: /^School wing/ }).first().click();
await page.getByPlaceholder("Riverside Festival 2026").fill("Spring open day");
await page.getByRole("button", { name: "Create project" }).click();
await page.waitForURL(/\/p\/p_.*\/describe$/);
const pid = page.url().split("/p/")[1].split("/")[0];
await page.getByRole("radio", { name: /Standard/ }).click();
await page.getByRole("button", { name: "Test this plan" }).click();
await page.waitForURL(/\/p\/p_[^/]+\?session=/, { timeout: 900_000 });
const sid = new URL(page.url()).searchParams.get("session");
mark("prepare: Spring open day tested", true, `${pid} ${sid}`);
const t1 = Date.now();

// 0:00 the stakes
await page.goto(`${BASE}/`);
await page.getByTestId("real-case-itaewon_2022").click();
const card = page.getByTestId("real-case-card");
await card.waitFor({ timeout: 60_000 });
const c = await text(card);
await page.screenshot({ path: `${out}/demo-1-stakes.png` });
mark("1 stakes", /159 people died and 196 were injured/.test(c) && /3\.2 m alley/.test(c));

// 0:20 describe a venue
await page.goto(`${BASE}/`);
await page.getByRole("button", { name: /^Describe it/ }).first().click();
await page.getByRole("textbox").first().fill("Metro station: underground platform level 120 x 14 m with 800 waiting passengers, three stairs up to the street-level ticket hall, which has exits on the west and east.");
await page.getByRole("button", { name: "Just draw my venue" }).click();
await page.waitForURL(/\/describe$/, { timeout: 300_000 }).catch(() => {});
const metro = (await (await fetch(`${BASE}/api/v1/projects/${page.url().split("/p/")[1].split("/")[0]}`)).json()).version.venue;
await page.waitForTimeout(2500);
await page.screenshot({ path: `${out}/demo-2-describe.png` });
mark("2 describe", metro.floors.length === 2 && (metro.stairs ?? []).length === 3, `${metro.floors.length} levels, ${(metro.stairs ?? []).length} stairs`);

// 0:50 the agents attack: Sandboxes tab, AI-written scenario, Show the code, badge, Scripts refusal
await page.goto(`${BASE}/p/${pid}?session=${sid}&tab=sandboxes`);
const tab = page.getByTestId("sandboxes-tab");
await tab.waitFor();
const scripts = await text(tab.getByTestId("sbx-script").first());
const aiWritten = /AI-written scenario/.test(scripts);
await tab.getByText("Show the code").first().click().catch(() => {});
await page.screenshot({ path: `${out}/demo-3a-code.png` });
mark("3a AI-written scenario + code", aiWritten, scripts.slice(0, 120));
await page.getByTestId("sandbox-badge").first().click();
const facts = await text(page.getByTestId("sandbox-facts"));
await page.screenshot({ path: `${out}/demo-3b-badge.png` });
mark("3b sandbox badge", /No network/.test(facts));
await page.keyboard.press("Escape");
await page.goto(`${BASE}/p/${pid}/scripts`);
await page.getByRole("button", { name: "New script" }).first().click();
await page.getByRole("textbox", { name: "Code" }).fill("import socket\n");
await page.getByRole("button", { name: "Run in sandbox" }).click();
const refused = await page.getByRole("listitem").filter({ hasText: /socket.* is not allowed/ }).waitFor({ timeout: 30_000 }).then(() => true, () => false);
await page.screenshot({ path: `${out}/demo-3c-refused.png` });
mark("3c unsafe script refused", refused);

// 1:40 the evidence
await page.goto(`${BASE}/p/${pid}?session=${sid}&tab=scenarios`);
const ev = page.getByTestId("evidence-panel");
await ev.waitFor({ timeout: 60_000 });
await ev.scrollIntoViewIfNeeded();
const e = await text(ev);
await page.screenshot({ path: `${out}/demo-4-evidence.png` });
mark("4 evidence", /Incident dataset/.test(e) && /Web search: off/.test(e));

// 2:10 the fix proved: Rewind
await page.goto(`${BASE}/p/${pid}?session=${sid}&tab=sandboxes`);
const rewind = page.getByRole("region", { name: "Rewind the worst moment" });
await rewind.getByRole("button", { name: "Rewind the worst moment" }).click();
await rewind.getByText(/Best from this second|No response did better/).waitFor({ timeout: 400_000 });
await rewind.scrollIntoViewIfNeeded();
await page.screenshot({ path: `${out}/demo-5-rewind.png` });
mark("5 rewind", (await rewind.getByRole("row").count()) >= 3, (await text(rewind.getByText(/Best from this second|No response did better/).first())));

// 2:40 the plan, the proof
await page.goto(`${BASE}/p/${pid}?session=${sid}&tab=handover`);
const href = await page.getByRole("link", { name: "Download checklist" }).first().getAttribute("href");
const checklist = await (await fetch(new URL(href, BASE))).text();
await page.goto(`${BASE}/help`);
await page.getByText("How good is the simulator?").first().click().catch(() => {});
await page.waitForTimeout(1500);
const help = await text(page.locator("main"));
await page.screenshot({ path: `${out}/demo-6-validation.png` });
mark("6 checklist + validation", checklist.includes("Planning aid, not a safety certification") && /within \d+% of the real crowd/.test(help));
console.log(`beats took ${((Date.now() - t1) / 1000).toFixed(0)} s (the video cuts the waiting)`);
await browser.close();
