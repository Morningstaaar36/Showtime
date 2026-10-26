import { describe, expect, it } from "vitest";
import type { RunResult } from "@/api/types";
import { thresholdsOf, tierLabel, verdictOf } from "./verdict";

const thresholds = thresholdsOf({});
const run = (fields: Partial<RunResult> = {}) => ({
  run_id: "r_test", tier: 3, status: "ok", provider: "docker", engine: "jupedsim",
  metrics: { agents_total: 20, agents_not_evacuated: 0, peak_density_ppm2: 1, time_above_danger_s: 0 },
  ...fields,
}) as RunResult;

describe("evidence labels", () => {
  it("never calls a fake sandbox a confirmed simulation or passing plan", () => {
    const result = run({ provider: "fake", engine: "fake" });
    expect(tierLabel(result)).toContain("Preview only");
    expect(verdictOf(result, thresholds, (id) => id).level).toBe("unknown");
  });
  it.each(["failed", "timeout", "cancelled", "running", "queued"] as const)("does not pass %s results", (status) => {
    expect(verdictOf(run({ status }), thresholds, (id) => id).level).toBe("unknown");
    expect(tierLabel(run({ status }))).not.toContain("Confirmed");
  });
  it("labels runs by the backend basis and never as confirmed", () => {
    expect(tierLabel(run({ basis: "completed_simulation" }))).toMatch(/^Full simulation \(run /);
    expect(tierLabel(run({ tier: 2, basis: "partial_simulation" }))).toMatch(/^Quick simulation/);
    expect(tierLabel(run({ basis: "unknown", status: "failed" }))).not.toContain("Confirmed");
    expect(tierLabel(run())).toMatch(/^Full simulation/); // older results without a basis
  });
  it("judges a quick simulation by how many got out before it stopped, not by who is still walking", () => {
    const quick = (frac: number) => run({
      tier: 2, sim_time_s: 180,
      metrics: { agents_total: 1500, agents_not_evacuated: Math.round(1500 * (1 - frac)), peak_density_ppm2: 2, time_above_danger_s: 0, evac_time_p95_s: null, extra: { evacuated_fraction: frac } },
    } as unknown as Partial<RunResult>);
    const slow = verdictOf(quick(0.4), thresholds, (id) => id);
    expect(slow.level).toBe("fails");
    expect(slow.reasons).toEqual(["only 40% out when the quick simulation stopped at 3 min"]);
    expect(verdictOf(quick(0.7), thresholds, (id) => id).reasons).toEqual([]);
    // a full simulation that ends with people inside still fails on them
    expect(verdictOf(run({ metrics: { agents_total: 100, agents_not_evacuated: 40, peak_density_ppm2: 1, time_above_danger_s: 0 } } as unknown as Partial<RunResult>), thresholds, (id) => id).reasons)
      .toEqual(["40 people still inside at the end"]);
  });
  it("judges by the server's settings, not by numbers of its own", () => {
    const left = run({ metrics: { agents_total: 100, agents_not_evacuated: 3, peak_density_ppm2: 1, time_above_danger_s: 0, evac_time_p95_s: 60 } } as unknown as Partial<RunResult>);
    expect(verdictOf(left, thresholds, (id) => id).level).toBe("holds"); // 3 is within the default tolerance
    expect(verdictOf(left, thresholdsOf({ stuck_tolerance_people: 0 }), (id) => id).level).toBe("fails");
    const busy = run({ metrics: { agents_total: 100, agents_not_evacuated: 0, peak_density_ppm2: 1, time_above_danger_s: 0, time_above_warning_s: 20, evac_time_p95_s: 60 } } as unknown as Partial<RunResult>);
    expect(verdictOf(busy, thresholds, (id) => id).level).toBe("holds");
    expect(verdictOf(busy, thresholdsOf({ at_risk_warning_s: 10 }), (id) => id).level).toBe("at_risk");
  });
  it("does not pass a partial result with no recorded failure", () => {
    expect(verdictOf(run({ status: "partial" }), thresholds, (id) => id).level).toBe("unknown");
  });
  it("retains failures observed in a partial simulation", () => {
    const result = run({ status: "partial" });
    result.metrics.time_above_danger_s = 10;
    expect(verdictOf(result, thresholds, (id) => id).level).toBe("fails");
  });
  it("words an unfinished evacuation without a stray percent sign", () => {
    const none = run();
    none.metrics.agents_total = 1000;
    expect(verdictOf(none, thresholds, (id) => id).sentences[0]).toBe("Not all of 1,000 people got out within the simulated time.");
    const some = run();
    some.metrics.agents_total = 1000;
    some.metrics.extra = { evacuated_fraction: 0.874 };
    expect(verdictOf(some, thresholds, (id) => id).sentences[0]).toBe("87% of 1,000 people got out within the simulated time.");
  });
});
