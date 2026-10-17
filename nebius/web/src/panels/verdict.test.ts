import { describe, expect, it } from "vitest";
import type { RunResult } from "@/api/types";
import { tierLabel, verdictOf } from "./verdict";

const thresholds = { warn: 3.5, danger: 5, dangerMinS: 5 };
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
