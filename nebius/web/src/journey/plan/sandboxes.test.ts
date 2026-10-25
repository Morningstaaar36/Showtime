import { describe, expect, it } from "vitest";
import type { Attack } from "@/api/types";
import type { SessionView } from "@/api/useSessionStream";
import { sandboxRows, scriptOutcomes } from "./sandboxes";

const script = { attack_id: "A1", title: "Smoke spreads", events: [{ type: "script", code: "def on_step(v, a):\n    pass\n", every_s: 1 }] } as unknown as Attack;
const menu = { attack_id: "A2", title: "Door blocked", events: [{ type: "block_exit", exit_id: "e1", at_s: 0 }] } as unknown as Attack;
const nodes = {
  "atk:A1": { node_id: "atk:A1", parent_id: "base", kind: "attack", label: "Smoke spreads", run_id: "r1", status: "break", attack_id: "A1" },
  "atk:A2": { node_id: "atk:A2", parent_id: "base", kind: "attack", label: "Door blocked", run_id: "r2", status: "ok", attack_id: "A2" },
} as unknown as SessionView["nodes"];

describe("the plan's sandboxes view", () => {
  it("pairs each AI-written script with what its sandbox reported", () => {
    const view = { sandboxes: [{ run_id: "r1", label: "Smoke spreads", state: "refused" as const, elapsed_s: 0.8, script: { state: "refused" as const, reason: "it failed the safety check" } }], nodes };
    const out = scriptOutcomes(view, [script, menu]);
    expect(out).toHaveLength(1);
    expect(out[0].attack.attack_id).toBe("A1");
    expect(out[0].run?.script?.state).toBe("refused");
  });
  it("builds rows from finished runs for a test from before the live feed", () => {
    const runs = { r2: { run_id: "r2", status: "ok", tier: 2, provider: "docker", metrics: {}, is_break: false, break_reasons: [] } } as unknown as SessionView["runs"];
    const { rows, recorded } = sandboxRows({ sandboxes: [], runs, nodes });
    expect(recorded).toBe(false);
    expect(rows).toEqual([expect.objectContaining({ run_id: "r2", label: "Door blocked", state: "finished", provider: "docker" })]);
  });
});
