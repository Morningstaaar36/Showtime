import { describe, expect, it } from "vitest";
import { fmtClock, fmtDensity, fmtDuration, fmtHM, fmtLength, fmtMoney, fmtTokens } from "./format";

describe("format", () => {
  it("formats clocks, including negative (already too late)", () => {
    expect(fmtClock(134)).toBe("2:14");
    expect(fmtClock(3725)).toBe("1:02:05");
    expect(fmtClock(-65)).toBe("−1:05");
    expect(fmtClock(null)).toBe("–:––");
  });

  it("formats durations in prose", () => {
    expect(fmtDuration(42)).toBe("42 s");
    expect(fmtDuration(252)).toBe("4 min 12 s");
    expect(fmtDuration(180)).toBe("3 min");
  });

  it("uses the product vocabulary for density and converts units", () => {
    expect(fmtDensity(5, "metric")).toBe("5.0 people per m²");
    expect(fmtDensity(5, "imperial")).toBe("4.6 per 10 ft²");
    expect(fmtLength(3, "imperial")).toBe("9.8 ft");
  });

  it("formats cost and tokens for the cost meter", () => {
    expect(fmtMoney(0)).toBe("$0.00");
    expect(fmtMoney(0.0042)).toBe("$0.0042");
    expect(fmtMoney(1.239)).toBe("$1.24");
    expect(fmtTokens(950)).toBe("950");
    expect(fmtTokens(12_400)).toBe("12.4k");
  });

  it("reads hours and minutes from local ISO times", () => {
    expect(fmtHM("2026-10-16T10:44:00")).toBe("10:44");
    expect(fmtHM(null)).toBe("–");
  });
});
