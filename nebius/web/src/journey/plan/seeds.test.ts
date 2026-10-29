import { describe, expect, it } from "vitest";
import type { SeedCheck } from "@/api/types";
import { seedBasesText, seedRangeLines } from "./seeds";

const check = (range: SeedCheck["range"], bases: Record<string, number> = {}): SeedCheck =>
  ({ range, bases } as unknown as SeedCheck);

describe("seed range on Your plan", () => {
  it("reads like the allocation's example", () => {
    const lines = seedRangeLines(check({
      evac_time_p95_s: { min: 269, max: 282, median: 275, n: 4 },
      peak_density_ppm2: { min: 1.2, max: 1.5, median: 1.3, n: 4 },
      agents_not_evacuated: { min: 0, max: 0, median: 0, n: 4 },
    }))!;
    expect(lines).toEqual([
      "Evacuation time (95%): 4 min 29 s – 4 min 42 s over 4 seeds",
      "Peak density 1.2 – 1.5 people per m² over 4 seeds",
      "Everyone got out in all 4 runs",
    ]);
  });
  it("collapses equal ends and reports people left inside", () => {
    const lines = seedRangeLines(check({
      evac_time_p95_s: null,
      peak_density_ppm2: { min: 5.04, max: 5.04, median: 5.04, n: 2 },
      agents_not_evacuated: { min: 3, max: 12, median: 7, n: 2 },
    }))!;
    expect(lines).toEqual(["Peak density 5.0 people per m² over 2 seeds", "3 – 12 people still inside at the end over 2 seeds"]);
    expect(seedRangeLines(check(null))).toBeNull();
  });
  it("says what the range rests on", () => {
    expect(seedBasesText(check(null, { completed_simulation: 3, partial_simulation: 1 }), (b) => (b === "completed_simulation" ? "Full simulation" : "Quick simulation")))
      .toBe("3 × full simulation · 1 × quick simulation");
  });
});
