import { describe, expect, it } from "vitest";
import { itemNumbers, itemOutcome, rangeVerdict, type SensitivityItem, type SensitivityRecord, spreadText, type TogetherCheck, togetherText } from "./range";

const item = (over: Partial<SensitivityItem>): SensitivityItem => ({
  variant: "as_tested", label: "As tested", people_factor: 1, speed_factor: 1, run_id: "r_1", original: true,
  status: "ok", basis: "completed_simulation", tier: 3, progress: null, error: null, included: true, breaks: [],
  metrics: { evac_time_p95_s: 150, peak_density_ppm2: 2.4, agents_not_evacuated: 0, agents_total: 1200, time_above_danger_s: 0 },
  ...over,
});

const record = (over: Partial<SensitivityRecord> = {}): SensitivityRecord => ({
  session_id: "s_1", available: true, reason: null, key: null, status: "done", items: [item({})], done: 5, total: 5,
  range: null, holds_in_all: true, breaks_in: [], notes: [], ...over,
});

const check = (over: Partial<TogetherCheck>): TogetherCheck => ({
  status: "running", run_id: "r_t", fix_ids: ["F1"], attack_id: "A1", attack_title: "Gate lost", tier: 3, seed: 42,
  started_at: "2026-10-16T10:00:00", evaluation: null, error: null, ...over,
});

describe("sensitivity runs", () => {
  it("say whether each assumption holds, breaks, failed or is waiting", () => {
    expect(itemOutcome(item({}))).toBe("holds");
    expect(itemOutcome(item({ breaks: ["50 people still inside at the end"] }))).toBe("breaks");
    expect(itemOutcome(item({ status: "failed", included: false, metrics: null }))).toBe("failed");
    expect(itemOutcome(item({ status: "running", included: false }))).toBe("waiting");
    expect(itemOutcome(item({ status: "queued", included: false }))).toBe("waiting");
  });

  it("print their numbers like the other plan tables", () => {
    expect(itemNumbers(item({}))).toEqual({ evac_time_95_s: 150, peak_density_ppm2: 2.4, people_inside: 0, time_above_danger_s: 0 });
    expect(itemNumbers(item({ metrics: null }))).toBeUndefined();
  });
});

describe("the range", () => {
  it("shows min and max, or one value when they agree", () => {
    expect(spreadText({ min: 130, max: 170, median: 150, n: 5 }, "time")).toBe("2 min 10 s – 2 min 50 s");
    expect(spreadText({ min: 0, max: 0, median: 0, n: 5 }, "people")).toBe("0");
    expect(spreadText({ min: 2.04, max: 2.96, median: 2.4, n: 5 }, "density")).toBe("2.0 – 3.0 people per m²");
    expect(spreadText(null, "time")).toBe("–");
  });

  it("names the assumptions that break the plan, and never says it holds before every run finished", () => {
    expect(rangeVerdict(record())).toEqual({ tone: "egress", text: "The plan holds under every assumption tested." });
    expect(rangeVerdict(record({ holds_in_all: false, breaks_in: ["20% more people"] })).text).toBe("The plan breaks with: 20% more people.");
    expect(rangeVerdict(record({ holds_in_all: null })).tone).toBe("neutral");
    expect(rangeVerdict(record({ status: "running", done: 2 })).text).toBe("2 of 5 runs done…");
  });
});

describe("chosen changes together", () => {
  it("only counts a simulation, and says confirmed only when the evaluation does", () => {
    expect(togetherText(null)).toBeNull();
    expect(togetherText(check({}))?.tone).toBe("neutral");
    const done = togetherText(check({ status: "done", evaluation: { status: "partially_confirmed", before_basis: "completed_simulation", after_basis: "partial_simulation", reasons: [] } }));
    expect(done?.tone).toBe("egress");
    expect(done?.text).not.toContain("confirmed by full simulations");
    const confirmed = togetherText(check({ status: "done", evaluation: { status: "confirmed", before_basis: "completed_simulation", after_basis: "completed_simulation", reasons: [] } }));
    expect(confirmed?.text).toContain("confirmed by full simulations");
    expect(togetherText(check({ status: "preview" }))?.text).toContain("not simulated");
    expect(togetherText(check({ status: "failed", error: "Injected" }))?.text).toContain("Injected");
  });
});
