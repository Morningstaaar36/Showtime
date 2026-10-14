import { describe, expect, it } from "vitest";
import { failures, rowOutcome, type StressRecord, type StressRow, stressCounter, stressSummary } from "./stress";

const row = (over: Partial<StressRow>): StressRow => ({
  attack_id: "A1", attack: "Gate lost", variant: "Plan as it is", fix_id: null, seed: 42, run_id: "r_1",
  status: "ok", basis: "preview", metrics: { evac_time_95_s: 120 }, breaks: false, error: null, ...over,
});

const record = (over: Partial<StressRecord> = {}): StressRecord => ({
  id: "st_1", project_id: "p_1", status: "running", tier: 2, total: 60, done: 47, failed: 2, seeds: [42, 43],
  notes: [], parallel: 2, message: null,
  rows: [
    row({ breaks: true }),
    row({ seed: 43 }),
    row({ variant: "Marshals", breaks: true }),
    row({ variant: "Marshals", status: "failed", error: "Injected failure", breaks: null }),
    row({ status: "queued", breaks: null }),
  ],
  ...over,
});

describe("stress test at scale", () => {
  it("counts done, total and failed", () => {
    expect(stressCounter(record())).toEqual({ text: "47 of 60 done", failed: "2 failed", pct: 78 });
    expect(stressCounter(record({ status: "done", done: 60, failed: 0 })).text).toBe("Finished: 60 of 60 done");
  });

  it("keeps failures listed and leaves them out of the summary", () => {
    expect(failures(record()).map((r) => r.error)).toEqual(["Injected failure"]);
    expect(stressSummary(record())).toEqual([
      { variant: "Plan as it is", runs: 2, breaks: 1 },
      { variant: "Marshals", runs: 1, breaks: 1 },
    ]);
    expect(rowOutcome(row({ status: "queued" }))).toBe("waiting");
  });
});
