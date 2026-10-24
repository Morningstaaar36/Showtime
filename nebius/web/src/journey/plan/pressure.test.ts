import { describe, expect, it } from "vitest";
import type { DensityIndex } from "@/replay/density";
import { pressureRange } from "./pressure";

describe("turbulence layer", () => {
  it("finds the peak and sets the colour range from the index's own thresholds", () => {
    const idx = { times: [0, 1, 2], peak_series: [0.2, 1.8, 0.9], warn: 1, danger: 2 } as unknown as DensityIndex;
    const r = pressureRange(idx);
    expect(r.peak).toBe(1.8);
    expect(r.peakAtS).toBe(1);
    expect(r.max).toBeCloseTo(2.8);
    expect(pressureRange({ ...idx, peak_series: [] }).peak).toBeNull();
  });
  it("dates the peak by its place in the run and writes the unit as 1/s²", () => {
    const idx = { times: [0, 1, 2, 3, 4], peak_series: [0, 0.1, 0.5, 0.2, 0, 0, 0, 0, 0], warn: 0.01, danger: 0.02, unit: "1/s2" } as unknown as DensityIndex;
    const r = pressureRange(idx);
    expect(r.peakAtS).toBeCloseTo(1); // index 2 of 9 values over 4 s
    expect(r.unit).toBe("1/s²");
  });
  it("never sets the colour scale above what the 8-bit grid can hold", () => {
    const idx = { times: [0, 1], peak_series: [0.4, 1.1], warn: 0.01, danger: 0.02, scale: 0.001 } as unknown as DensityIndex;
    expect(pressureRange(idx).max).toBeCloseTo(0.255);
  });
});
