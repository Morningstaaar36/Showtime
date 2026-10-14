import { describe, expect, it } from "vitest";
import { basisLabel, evaluationLabel, isResultBasis, runBasisLabel, runOutcome } from "@/lib/evidence";

describe("runOutcome with the backend basis", () => {
  it("only a finished simulation can hold", () => {
    expect(runOutcome({ basis: "completed_simulation", is_break: false })).toBe("holds");
    expect(runOutcome({ basis: "completed_simulation", is_break: true })).toBe("break");
  });
  it("keeps breaks seen in a time-capped simulation, but never calls it a pass", () => {
    expect(runOutcome({ basis: "partial_simulation", is_break: true })).toBe("break");
    expect(runOutcome({ basis: "partial_simulation", is_break: false })).toBe("unknown");
  });
  it("instant estimates, previews and unfinished runs never pass or fail", () => {
    expect(runOutcome({ basis: "instant_estimate", is_break: true })).toBe("unknown");
    expect(runOutcome({ basis: "instant_estimate", is_break: false })).toBe("unknown");
    expect(runOutcome({ basis: "unknown", is_break: false })).toBe("unknown");
    expect(runOutcome({ basis: "preview", is_break: false })).toBe("preview");
  });
  it("prefers the basis over status fields that look like a pass", () => {
    // a fallback estimate reported with status ok must not hold
    expect(runOutcome({ basis: "instant_estimate", status: "ok", engine: "tier1", tier: 1 })).toBe("unknown");
    // people still inside: the backend says partial even though the status is ok
    expect(runOutcome({ basis: "partial_simulation", status: "ok", engine: "jupedsim", tier: 3 })).toBe("unknown");
  });
  it("falls back to the old rules for results stored without a basis", () => {
    expect(runOutcome({ status: "ok", engine: "jupedsim", tier: 3, is_break: false })).toBe("holds");
    expect(runOutcome({ status: "ok", engine: "jupedsim", tier: 1 })).toBe("unknown");
    expect(runOutcome({ status: "timeout", engine: "jupedsim", tier: 3 })).toBe("unknown");
    expect(runOutcome({ status: "ok", engine: "fake", provider: "fake", tier: 3 })).toBe("preview");
    expect(runOutcome({ status: "ok", tier: 3, basis: "made-up" })).toBe("unknown");
    expect(runOutcome(undefined)).toBe("unknown");
  });
});

describe("basisLabel", () => {
  it("uses plain organizer words", () => {
    expect(basisLabel("instant_estimate")).toBe("Instant estimate");
    expect(basisLabel("partial_simulation")).toBe("Quick simulation (first minutes only)");
    expect(basisLabel("completed_simulation")).toBe("Full simulation");
    expect(basisLabel("preview")).toBe("Preview (no simulator)");
    expect(basisLabel("unknown")).toBe("Unknown: the simulation didn't finish");
  });
  it("refines by tier", () => {
    expect(basisLabel("partial_simulation", 2)).toBe("Quick simulation (first minutes only)");
    expect(basisLabel("partial_simulation", 3)).toBe("Full simulation, stopped before everyone was out");
    expect(basisLabel("completed_simulation", 2)).toBe("Quick simulation (ran to the end)");
    expect(basisLabel("completed_simulation", 3)).toBe("Full simulation");
  });
  it("treats missing or unexpected values as unknown", () => {
    expect(basisLabel(undefined)).toBe("Unknown: the simulation didn't finish");
    expect(basisLabel("confirmed")).toBe("Unknown: the simulation didn't finish");
    expect(isResultBasis("confirmed")).toBe(false);
    expect(isResultBasis("preview")).toBe(true);
  });
  it("never says confirmed", () => {
    for (const b of ["instant_estimate", "partial_simulation", "completed_simulation", "preview", "unknown"]) {
      for (const tier of [undefined, 1, 2, 3]) expect(basisLabel(b, tier).toLowerCase()).not.toContain("confirm");
    }
  });
});

describe("runBasisLabel", () => {
  it("labels an estimate shown in place of a failed simulation", () => {
    expect(runBasisLabel({ basis: "instant_estimate", fallback_for: "r_1" })).toBe("Instant estimate (the simulation didn't finish)");
    expect(runBasisLabel({ basis: "instant_estimate", extensions: { fallback_for: "r_1" } })).toBe("Instant estimate (the simulation didn't finish)");
    expect(runBasisLabel({ basis: "partial_simulation", tier: 3 })).toBe("Full simulation, stopped before everyone was out");
    expect(runBasisLabel(null)).toBe("Unknown: the simulation didn't finish");
  });
});

describe("evaluationLabel", () => {
  it("names each evaluation status", () => {
    expect(evaluationLabel({ status: "confirmed" })).toBe("Confirmed by full simulations");
    expect(evaluationLabel({ status: "partially_confirmed" })).toBe("Partly confirmed: the simulations stopped before everyone was out");
    expect(evaluationLabel({ status: "unconfirmed" })).toBe("Not confirmed");
    expect(evaluationLabel({ status: "failed" })).toBe("Confirmation failed: the simulations didn't finish");
  });
  it("never confirms a session that has no evaluation", () => {
    expect(evaluationLabel(undefined)).toBe("Not confirmed");
    expect(evaluationLabel(null)).toBe("Not confirmed");
    expect(evaluationLabel({ status: "something-else" })).toBe("Not confirmed");
  });
});
