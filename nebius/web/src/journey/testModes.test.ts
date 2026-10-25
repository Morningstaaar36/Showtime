import { afterEach, describe, expect, it, vi } from "vitest";
import { TEST_MODES, saveTestMode, savedTestMode, testMode } from "./testModes";

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("test modes", () => {
  it("falls back to the standard test for an unknown or missing mode", () => {
    expect(testMode("nope").id).toBe("standard");
    expect(testMode(null).id).toBe("standard");
    expect(testMode("deep").id).toBe("deep");
  });

  it("remembers the last mode in this browser", () => {
    expect(savedTestMode().id).toBe("standard");
    saveTestMode("offline");
    expect(savedTestMode().id).toBe("offline");
  });

  it("keeps working when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(() => saveTestMode("deep")).not.toThrow();
    expect(savedTestMode().id).toBe("standard");
  });

  it("every mode simulates attacks and fixes; only offline goes without the AI", () => {
    for (const m of TEST_MODES) {
      expect(m.config.attacks_per_round as number).toBeGreaterThan(0);
      expect(m.config.fixes_per_attack as number).toBeGreaterThan(0);
      expect(m.config.agents).toBe(m.id === "offline" ? "rules" : "model");
    }
    expect(testMode("deep").config.max_rounds as number).toBeGreaterThan(testMode("standard").config.max_rounds as number);
    expect(testMode("quick").config.attacks_per_round as number).toBeLessThan(testMode("standard").config.attacks_per_round as number);
  });
});
