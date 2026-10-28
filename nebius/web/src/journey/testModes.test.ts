import { afterEach, describe, expect, it, vi } from "vitest";
import { saveTestMode, savedTestMode, testMode, testModesOf } from "./testModes";

// the list the page uses until GET /test_modes answers
const fallback = testModesOf(undefined);

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("test modes", () => {
  it("falls back to the standard test for an unknown or missing mode", () => {
    expect(testMode("nope", fallback).id).toBe("standard");
    expect(testMode(null, fallback).id).toBe("standard");
    expect(testMode("deep", fallback).id).toBe("deep");
  });

  it("remembers the last mode in this browser", () => {
    expect(savedTestMode(fallback).id).toBe("standard");
    saveTestMode("offline");
    expect(savedTestMode(fallback).id).toBe("offline");
  });

  it("keeps working when storage is blocked", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(() => saveTestMode("deep")).not.toThrow();
    expect(savedTestMode(fallback).id).toBe("standard");
  });

  it("every mode simulates attacks and fixes; only offline goes without the AI", () => {
    for (const m of fallback.modes) {
      expect(m.config.attacks_per_round as number).toBeGreaterThan(0);
      expect(m.config.fixes_per_attack as number).toBeGreaterThan(0);
      expect(m.config.agents).toBe(m.id === "offline" ? "rules" : "model");
    }
    expect(testMode("deep", fallback).config.max_rounds as number).toBeGreaterThan(testMode("standard", fallback).config.max_rounds as number);
    expect(testMode("quick", fallback).config.attacks_per_round as number).toBeLessThan(testMode("standard", fallback).config.attacks_per_round as number);
  });

  it("uses the server's list and default once it answers, keeping a saved mode only it knows", () => {
    const server = testModesOf({ default: "quick", modes: [
      { id: "quick", minutes: 1, config: { max_rounds: 1 } },
      { id: "overnight", minutes: 60, config: { max_rounds: 5 } },
    ] });
    expect(testMode(null, server).id).toBe("quick");
    saveTestMode("overnight");
    expect(savedTestMode(server).minutes).toBe(60);
    expect(savedTestMode(fallback).id).toBe("standard");
    expect(testModesOf({ default: "x", modes: [] })).toBe(fallback);
  });
});
