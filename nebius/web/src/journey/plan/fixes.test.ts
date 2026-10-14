import { describe, expect, it } from "vitest";
import type { Fix } from "@/api/types";
import { acceptBody, evacValue, fixDependencies, fixSource, fixTest, testedTogether, toggleFix } from "./fixes";

const fix = (fix_id: string, more: Partial<Fix> = {}): Fix =>
  ({ fix_id, for_attack: "A1", title: fix_id, patch: { ops: [] }, operational: [], actions: [], replace_actions: [],
     remove_action_ids: [], new_objects: {}, extensions: {}, ...more }) as unknown as Fix;

const door = fix("F1", { patch: { ops: [{ op: "add_exit", floor_id: "F0", id: "door_e1", wall: "east", width_m: 2 }] } as unknown as Fix["patch"],
  extensions: { generated_by: "rules" } });
const wider = fix("F2", { patch: { ops: [{ op: "resize", target: "door_s2", width_m: 3 }] } as unknown as Fix["patch"] });
const marshals = fix("F3", { operational: [{ type: "marshal_redirect", to_exit_id: "door_e1", at_s: 20 }] as Fix["operational"] });
const kept = [door, wider, marshals];
const ids = kept.map((f) => f.fix_id);

describe("where a fix came from", () => {
  it("tells standard rules from the AI's ideas", () => {
    expect(fixSource(door)).toBe("rules");
    expect(fixSource(wider)).toBe("ai");
  });
});

describe("choosing fixes", () => {
  const deps = fixDependencies(kept);

  it("finds fixes that build on what an earlier fix adds", () => {
    expect(deps).toEqual({ F1: [], F2: [], F3: ["F1"] });
  });

  it("a staffed action can build on an action an earlier fix added", () => {
    const hold = fix("F4", { actions: [{ action_id: "hold", start_s: 0, end_s: 60, target_ids: [], depends_on: [], required_approvals: [], resources: [], source: "agent", label: "" }] as unknown as Fix["actions"] });
    const after = fix("F5", { actions: [{ action_id: "open", start_s: 60, end_s: 90, target_ids: [], depends_on: ["hold"], required_approvals: [], resources: [], source: "agent", label: "" }] as unknown as Fix["actions"] });
    expect(fixDependencies([hold, after])).toEqual({ F4: [], F5: ["F4"] });
  });

  it("leaving a fix out also leaves out what builds on it", () => {
    const all = new Set(ids);
    expect([...toggleFix(all, "F1", deps)].sort()).toEqual(["F2"]);
    expect([...toggleFix(all, "F2", deps)].sort()).toEqual(["F1", "F3"]);
  });

  it("choosing a fix also chooses what it builds on", () => {
    expect([...toggleFix(new Set(["F2"]), "F3", deps)].sort()).toEqual(["F1", "F2", "F3"]);
    expect([...toggleFix(new Set(), "F1", deps)]).toEqual(["F1"]);
  });

  it("sends nothing extra for every fix, else the chosen ids in kept order", () => {
    expect(testedTogether(new Set(ids), ids)).toBe(true);
    expect(acceptBody(new Set(ids), ids)).toEqual({});
    expect(testedTogether(new Set(["F3", "F1"]), ids)).toBe(false);
    expect(acceptBody(new Set(["F3", "F1"]), ids)).toEqual({ fix_ids: ["F1", "F3"] });
    expect(testedTogether(new Set(), [])).toBe(false);
  });
});

describe("a fix's own test", () => {
  const nodes = {
    "atk:A1": { run_id: "r_atk", basis: "partial_simulation", tier: 2 },
    "atk:A1:current:1": { run_id: "r_atk_again", basis: "partial_simulation", tier: 2 },
    "fix:F1": { run_id: "r_f1", basis: "partial_simulation", tier: 2 },
    "fix:F2": { run_id: "r_f2", basis: "preview", tier: 2 },
  };

  it("compares with the attack run on the venue it was tried on", () => {
    expect(fixTest(door, 0, nodes)).toEqual({ attackId: "A1", before: nodes["atk:A1"], after: nodes["fix:F1"] });
    // an earlier fix of the round was kept: the attack was run again first
    expect(fixTest(wider, 1, nodes).before?.run_id).toBe("r_atk_again");
    expect(fixTest(marshals, 2, nodes)).toEqual({ attackId: "A1", before: nodes["atk:A1"], after: null });
  });

  it("labels an extrapolated evacuation time as estimated", () => {
    expect(evacValue({ evac_time_p95_s: 245 })).toBe("4 min 5 s");
    expect(evacValue({ evac_time_p95_s: null, evac_time_estimate_s: 180 })).toBe("about 3 min (estimated)");
    expect(evacValue({ evac_time_p95_s: null })).toBe("Not reached");
    expect(evacValue(null)).toBe("–");
  });
});
