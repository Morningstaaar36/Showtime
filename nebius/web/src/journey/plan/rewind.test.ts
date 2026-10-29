import { describe, expect, it } from "vitest";
import { bestLine, deltaText, deltaTone, metricText, type RewindRecord, rewindProgress, rewindRows } from "./rewind";

const record = (over: Partial<RewindRecord> = {}): RewindRecord => ({
  id: "rw_1", session_id: "s_1", project_id: "p_1", status: "done", message: null,
  attack: { attack_id: "A1", title: "West stairwell lost" },
  moment: { at_s: 75, why: "peak density 6.2 people per m² at 75 s", source: "hotspot" },
  source_run_id: "r_src", checkpoint_run_id: "r_ckpt", tier: 3, done: 3, total: 3, best: "hold:z",
  notes: [],
  branches: [
    { key: "nothing", label: "Do nothing", kind: "nothing", events: [], run_id: "r_a", status: "ok", basis: "completed_simulation",
      metrics: { evac_time_95_s: 177.6, people_inside: 0, peak_density_ppm2: 4.74, time_above_danger_s: 12 } },
    { key: "hold:z", label: "Hold Classroom 1 back for one minute", kind: "quick_action", events: [], run_id: "r_b", status: "ok",
      basis: "completed_simulation", comparable: true, better: true,
      metrics: { evac_time_95_s: 214.8, people_inside: 0, peak_density_ppm2: 4.48, time_above_danger_s: 0 },
      vs_nothing: { evac_time_95_s: 37.2, people_inside: 0, peak_density_ppm2: -0.26, time_above_danger_s: -12 } },
    { key: "fix:F1", label: "Kept change: marshals", kind: "kept_fix", events: [], status: "not_possible", error: "no staff free" },
    { key: "open:x", label: "Open West stairwell again", kind: "quick_action", events: [], run_id: "r_c", status: "failed", error: "crashed" },
  ],
  ...over,
});

describe("rewind comparison", () => {
  it("puts do nothing first and highlights the best response", () => {
    const rows = rewindRows(record());
    expect(rows.map((r) => r.key)).toEqual(["nothing", "hold:z", "fix:F1", "open:x"]);
    expect(rows[0].nothing && rows[0].cells.every((c) => c.delta === "")).toBe(true);
    expect(rows[1].best).toBe(true);
    expect(rows[1].evidence).toBe("Full simulation");
    expect(bestLine(record())).toBe("Best from this second: Hold Classroom 1 back for one minute.");
  });

  it("shows each change against do nothing, lower is better", () => {
    const cells = rewindRows(record())[1].cells;
    expect(cells.map((c) => c.delta)).toEqual(["+37 s", "same", "−0.3", "−12 s"]);
    expect(cells.map((c) => c.tone)).toEqual(["worse", "same", "better", "better"]);
    expect(deltaTone("peak_density_ppm2", 0.01)).toBe("same");
    expect(deltaText("evac_time_95_s", -75)).toBe("−1 min 15 s");
  });

  it("keeps branches without numbers listed with the reason", () => {
    const rows = rewindRows(record());
    expect(rows[2].problem).toBe("Not possible here: no staff free");
    expect(rows[3].problem).toBe("Didn't finish: crashed");
    expect(rows[3].cells.every((c) => c.value === "–")).toBe(true);
  });

  it("says what is happening while it runs", () => {
    expect(rewindProgress(record({ status: "running", checkpoint_run_id: null, total: 0, done: 0 }))).toBe("Saving the crowd at 1 min 15 s into the event…");
    expect(rewindProgress(record({ status: "running", total: 4, done: 1 }))).toBe("1 of 4 responses done");
    expect(bestLine(record({ best: null }))).toBe("No response did better than doing nothing from this second.");
  });

  it("formats values in plain units", () => {
    expect(metricText("peak_density_ppm2", { peak_density_ppm2: 4.74 })).toBe("4.7 people per m²");
    expect(metricText("evac_time_95_s", { evac_time_95_s: 90, evac_is_estimate: true })).toBe("about 1 min 30 s");
    expect(metricText("evac_time_95_s", { evac_time_95_s: null })).toBe("not everyone got out");
  });
});
