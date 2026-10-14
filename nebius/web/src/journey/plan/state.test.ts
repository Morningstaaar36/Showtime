import { describe, expect, it } from "vitest";
import type { AppliedRecord } from "@/api/types";
import { planState } from "./state";

const record = (plan_hash: string, tested_together: boolean): AppliedRecord =>
  ({ version: 4, plan_hash, fix_ids: ["F1"], tested_together, note: tested_together ? null : "not together", at: "" });

describe("where the current plan stands", () => {
  it("is untested without both identities", () => {
    expect(planState({ currentHash: "h1", testedHash: null, kept: 2 }).state).toBe("none");
  });
  it("is waiting for a decision while it is the tested plan", () => {
    expect(planState({ currentHash: "h1", testedHash: "h1", kept: 2 }).state).toBe("pending");
    expect(planState({ currentHash: "h1", testedHash: "h1", kept: 0 }).state).toBe("tested");
  });
  it("knows the version saved from the kept fixes, and whether they were tested together", () => {
    const all = record("h2", true);
    const some = record("h3", false);
    expect(planState({ currentHash: "h2", testedHash: "h1", kept: 2, applied: [all, some] })).toEqual({ state: "accepted", record: all });
    expect(planState({ currentHash: "h3", testedHash: "h1", kept: 2, applied: [all, some] })).toEqual({ state: "accepted_subset", record: some });
  });
  it("falls back to the final run's identity for versions saved before records existed", () => {
    expect(planState({ currentHash: "h2", testedHash: "h1", kept: 2, fixedHash: "h2" }).state).toBe("accepted");
  });
  it("is stale after any other change", () => {
    expect(planState({ currentHash: "h9", testedHash: "h1", kept: 2, applied: [record("h2", true)], fixedHash: "h2" }).state).toBe("stale");
  });
});
