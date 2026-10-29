import { test as base } from "@playwright/test";

export * from "@playwright/test";

// The API refuses a change (POST, PUT, PATCH, DELETE) without the app's header (api/app/main.py,
// WRITE_HEADER). The specs' own API calls carry it; the page's requests send it from the app.
export const SHOWTIME_HEADERS = { "X-Showtime": "1" };

export const test = base.extend({
  request: async ({ playwright, baseURL }, provide) => {
    const request = await playwright.request.newContext({ baseURL, extraHTTPHeaders: SHOWTIME_HEADERS });
    await provide(request);
    await request.dispose();
  },
});
