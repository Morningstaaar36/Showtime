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
});
