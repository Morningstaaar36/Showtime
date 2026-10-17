import { describe, expect, it } from "vitest";
import { MAX_RECONNECTS, reconnectDelay } from "./reconnect";

describe("reconnectDelay", () => {
  it("retries a first drop after 2 s and backs off up to 30 s", () => {
    expect([1, 2, 3, 4, 5, 6].map(reconnectDelay)).toEqual([2000, 4000, 8000, 16000, 30000, 30000]);
  });
  it("gives up after the last allowed attempt", () => {
    expect(reconnectDelay(MAX_RECONNECTS)).toBe(30000);
    expect(reconnectDelay(MAX_RECONNECTS + 1)).toBeNull();
    expect(reconnectDelay(0)).toBeNull();
  });
});
