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
  it("does not pass a partial result with no recorded failure", () => {
    expect(verdictOf(run({ status: "partial" }), thresholds, (id) => id).level).toBe("unknown");
  });
  it("retains failures observed in a partial simulation", () => {
    const result = run({ status: "partial" });
    result.metrics.time_above_danger_s = 10;
    expect(verdictOf(result, thresholds, (id) => id).level).toBe("fails");
  });
});
