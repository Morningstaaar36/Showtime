// A guided tour in a visible Chrome window: the 3-minute demo (docs/DEMO.md), clicked step by
// step, with a caption on screen saying what each step shows. The window stays open at the end.
// Usage: node e2e/demo-tour.mjs <project id> <session id>   (app running at BASE)
import { chromium } from "@playwright/test";

const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [pid, sid] = process.argv.slice(2);
const SLOW = Number(process.env.TOUR_PAUSE_MS ?? 4500);

const browser = await chromium.launch({
  headless: false,
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE ?? "/usr/bin/google-chrome",
  slowMo: 120,
  args: ["--start-maximized"],
});
const context = await browser.newContext({ viewport: null });
// a caption bar at the top of every page, set with window.__caption(text)
await context.addInitScript(() => {
  window.__caption = (text) => {
    let el = document.getElementById("__tour_caption");
    if (!el) {
      el = document.createElement("div");
      el.id = "__tour_caption";
      el.style.cssText = "position:fixed;left:50%;bottom:24px;transform:translateX(-50%);z-index:2147483647;" +
        "max-width:min(900px,90vw);padding:14px 22px;border-radius:12px;background:rgba(20,22,40,.92);color:#fff;" +
        "font:600 17px/1.45 system-ui,sans-serif;box-shadow:0 10px 30px rgba(0,0,0,.35);pointer-events:none;text-align:center";
      document.body.appendChild(el);
    }
    el.textContent = text;
  };
});
const page = await context.newPage();
const pause = (ms = SLOW) => page.waitForTimeout(ms);
const say = async (text, ms = SLOW) => {
  await page.evaluate((t) => window.__caption?.(t), text).catch(() => {});
  await pause(ms);
};
const smoothTo = async (loc) => {
  await loc.evaluate((el) => el.scrollIntoView({ behavior: "smooth", block: "center" })).catch(() => {});
  await pause(1200);
};

// --- 0:00 the stakes -------------------------------------------------------------------------
await page.goto(`${BASE}/`);
await say("Showtime: AI agents try to break your event plan. Every attack runs in a sealed sandbox, and a physics simulator decides what breaks.", 6000);
const tile = page.getByTestId("real-case-itaewon_2022");
await smoothTo(tile);
await say("1 · The stakes. Real crowd disasters, rebuilt by the AI from sourced descriptions. Let's open Itaewon (2022).");
await tile.click();
const card = page.getByTestId("real-case-card");
await card.waitFor({ timeout: 60_000 });
await smoothTo(card);
await say("159 people died in a 3.2 m alley. The card cites its sources, and shows where this rebuild's simulation put its peak density.", 7000);

// --- 0:20 describe a venue in one sentence ---------------------------------------------------
await page.goto(`${BASE}/`);
await say("2 · Describe a venue in one sentence. No stage needed: here a metro station on two levels.");
await page.getByRole("button", { name: /^Describe it/ }).first().click();
const box = page.getByRole("textbox").first();
await smoothTo(box);
await box.click();
await page.keyboard.type("Metro station: underground platform level 120 x 14 m with 800 waiting passengers, three stairs up to the street-level ticket hall, which has exits on the west and east.", { delay: 18 });
await pause(1000);
await page.getByRole("button", { name: "Just draw my venue" }).click();
await say("A Nemotron agent writes the design; a solver builds every wall, stair and exit; checks send errors back to the model.", 3000);
await page.waitForURL(/\/describe$/, { timeout: 300_000 });
await say("Check your venue: two levels, three stairs, two street exits, 800 people on the platform.", 7000);

// --- 0:50 the agents attack ------------------------------------------------------------------
await page.goto(`${BASE}/p/${pid}/work?session=${sid}`);
await say("3 · The agents attack. This is AI at work for a finished test of the school wing ('Spring open day').", 5000);
const feed = page.getByTestId("sandbox-feed");
if (await feed.count()) {
  await smoothTo(feed);
  await say("Every run is its own throwaway container: no network, memory and process limits, no keys. Each row: its state and its time.", 7000);
}
const tools = page.getByTestId("tool-calls");
if (await tools.count()) {
  await smoothTo(tools);
  await say("The agents' tool calls: what they aimed at, the incident dataset lookup, and web search (off until a Tavily key is added).", 6500);
}
await page.goto(`${BASE}/p/${pid}?session=${sid}&tab=sandboxes`);
const tab = page.getByTestId("sandboxes-tab");
await tab.waitFor();
await say("The plan's Sandboxes tab: the scenario the AI wrote as code, and what happened when it ran.");
const code = tab.getByText("Show the code").first();
await smoothTo(code);
await code.click();
await say("This attack is a Python script the red team wrote. It only ever ran inside the sandbox; the simulator, not the AI, decided what broke.", 7500);
await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
await pause(800);
await page.getByTestId("sandbox-badge").first().click();
await say("The sandbox badge in the header says what every sandbox guarantees.", 6000);
await page.keyboard.press("Escape");

await page.goto(`${BASE}/p/${pid}/scripts`);
await say("Now try something unsafe: a script that imports socket to reach the network.");
await page.getByRole("button", { name: "New script" }).first().click();
const code2 = page.getByRole("textbox", { name: "Code" });
await code2.click();
await page.keyboard.type("import socket\nsocket.create_connection(('example.org', 80))\n", { delay: 35 });
await page.getByRole("button", { name: "Run in sandbox" }).click();
const why = page.getByRole("listitem").filter({ hasText: /socket.* is not allowed/ });
await why.waitFor({ timeout: 30_000 });
await smoothTo(why);
await say("Refused before it runs, with the reason. And the sandbox has no network anyway: Help › Sandbox lists 14 attacks and what stopped each.", 7500);

// --- 1:40 the evidence -----------------------------------------------------------------------
await page.goto(`${BASE}/p/${pid}?session=${sid}&tab=scenarios`);
const ev = page.getByTestId("evidence-panel");
await ev.waitFor({ timeout: 60_000 });
await smoothTo(ev);
await say("4 · The evidence. Each attack is grounded in a real crowd accident from the incident dataset, and every source says where it came from.", 7500);
await say("Live web search switches on with a Tavily key. Today it's off, and the screen says so: nothing claims a web result that didn't happen.", 6500);

// --- 2:10 the fix proved in a sandbox --------------------------------------------------------
await page.goto(`${BASE}/p/${pid}?session=${sid}&tab=sandboxes`);
const rewind = page.getByRole("region", { name: "Rewind the worst moment" });
await rewind.waitFor();
await smoothTo(rewind);
await say("5 · The fix, proved in a sandbox. Rewind to the worst second, then run 'do nothing' and each response from that same second.");
const again = rewind.getByRole("button", { name: /Rewind (the worst moment|again)/ }).first();
await again.click();
await say("Each response runs in its own sandbox branch…", 3000);
await rewind.getByText(/Best from this second|No response did better/).waitFor({ timeout: 400_000 });
await smoothTo(rewind.getByRole("table"));
await say("…and the table shows the measured difference against doing nothing. Every number comes from the simulator.", 8000);

// --- 2:40 the plan, the proof ----------------------------------------------------------------
await page.goto(`${BASE}/p/${pid}?session=${sid}&tab=handover`);
await say("6 · Hand over: the report and a printable checklist for the stewards.");
const [checklist] = await Promise.all([
  context.waitForEvent("page"),
  page.getByRole("link", { name: "Download checklist" }).first().click(),
]);
await checklist.waitForLoadState();
await checklist.evaluate(() => window.__caption?.("The handover checklist: open conditions to tick off, staff actions, key numbers, sign-off. Planning aid, not a safety certification."));
await checklist.waitForTimeout(8000);
await checklist.close();

await page.goto(`${BASE}/help`);
await page.getByText("How good is the simulator?").first().click().catch(() => {});
await pause(1200);
await say("The simulator is checked against a real bottleneck experiment (Jülich): its flow is within a few per cent of the real crowd's.", 8000);
await page.goto(`${BASE}/team`);
await say("Twelve NVIDIA Nemotron agents, the model each runs on, and the tools each may use. Nebius Token Factory and Sandboxes plug in through .env.", 8000);
await page.goto(`${BASE}/`);
await say("That's the demo. Planning aid, not a safety certification. Close this window when you're done.", 4000);

// keep the window open until it is closed
await new Promise((resolve) => browser.on("disconnected", resolve));
