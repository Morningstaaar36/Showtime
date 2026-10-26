// Demo beat 3c alone: the Scripts page refuses `import socket`; also reads the header badges' look.
// Usage: node e2e/explore-scripts-beat.mjs <outdir> <project id>
import { chromium } from "@playwright/test";
const BASE = process.env.BASE ?? "http://127.0.0.1:5173";
const [out, pid] = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1600, height: 900 } });
await page.goto(`${BASE}/p/${pid}/scripts`);
await page.waitForTimeout(1500);
const badges = await page.evaluate(() => [...document.querySelectorAll("header button")].filter((b) => /OPENROUTER|DOCKER|LOCAL|NEBIUS/.test(b.textContent ?? "")).map((b) => `${b.textContent?.trim()} :: ${b.className.toString().slice(0, 160)}`));
console.log(badges.join("\n"));
await page.getByRole("button", { name: "New script" }).first().click();
await page.getByRole("textbox", { name: "Code" }).fill("import socket\n");
await page.getByRole("button", { name: "Run in sandbox" }).click();
const ok = await page.getByRole("listitem").filter({ hasText: /socket.* is not allowed/ }).waitFor({ timeout: 30_000 }).then(() => true, () => false);
await page.screenshot({ path: `${out}/demo-3c-refused.png` });
console.log(ok ? "PASS 3c unsafe script refused" : "FAIL 3c");
await browser.close();
