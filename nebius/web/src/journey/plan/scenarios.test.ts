import { describe, expect, it } from "vitest";
import type { Attack, Fix } from "@/api/types";
import type { RunInfo, TreeNode } from "@/api/useSessionStream";
import { Trajectory, type TrajIndex } from "@/replay/trajectory";
import { captionAt, eventCaption, peoplePerFloor, scenarioMarkers, scenarioRows } from "./scenarios";

const node = (node_id: string, kind: TreeNode["kind"], extra: Partial<TreeNode> = {}): TreeNode =>
  ({ node_id, kind, parent_id: null, label: node_id, run_id: `r_${node_id}`, status: "ok", ...extra });
const run = (id: string, evac: number, isBreak: boolean): RunInfo =>
  ({ run_id: id, status: "ok", tier: 3, provider: "docker", engine: "jupedsim", metrics: { evac_time_p95_s: evac, peak_density_ppm2: 4.2 }, is_break: isBreak, break_reasons: [] });
const attack = (id: string, title: string, events: Attack["events"]): Attack =>
  ({ attack_id: id, title, events, inspired_by: { incident: "x", source_url: "https://example.org" } } as unknown as Attack);
const names = (id: string) => ({ door_s1: "South door 1", aud: "Audience", door_e: "East door" } as Record<string, string>)[id] ?? id;

describe("tested scenarios", () => {
  const nodes: Record<string, TreeNode> = {
    baseline: node("baseline", "baseline"),
    "atk:A2": node("atk:A2", "attack", { attack_id: "A2", parent_id: "baseline" }),
    "atk:A1": node("atk:A1", "attack", { attack_id: "A1", parent_id: "baseline" }),
    "fix:F1": node("fix:F1", "fix", { fix_id: "F1", parent_id: "atk:A1", accepted: true }),
    "final:before": node("final:before", "final", { attack_id: "A1" }),
    "final:after": node("final:after", "final", { attack_id: "A1", status: "running" }),
    "atk:A1:current:1": node("atk:A1:current:1", "attack", { attack_id: "A1" }),
  };
  const runs = { r_baseline: run("r_baseline", 200, false), "r_atk:A1": run("r_atk:A1", 400, true), "r_fix:F1": run("r_fix:F1", 250, false) };
  const attacks = [attack("A1", "South door blocked", [] as unknown as Attack["events"]), attack("A2", "Surge", [] as unknown as Attack["events"])];
  const fixes = [{ fix_id: "F1", for_attack: "A1", title: "Open the east door", operational: [] } as unknown as Fix];
  const rows = scenarioRows(nodes, runs, attacks, fixes);

  it("lists the plan, each attack with its fixes, then the final check", () => {
    expect(rows.map((r) => r.title)).toEqual([
      "Your plan as drawn", "South door blocked", "South door blocked · with the changes kept so far", "Surge",
      "Final check before the changes · South door blocked", "Final check with the changes · South door blocked",
    ]);
    expect(rows[1].children.map((c) => [c.title, c.accepted, c.outcome])).toEqual([["Open the east door", true, "holds"]]);
  });
  it("gives each row its verdict and numbers", () => {
    expect(rows[0]).toMatchObject({ outcome: "holds", evacS: 200, peak: 4.2 });
    expect(rows[1]).toMatchObject({ outcome: "break", evacS: 400, runId: "r_atk:A1" });
    expect(rows[3].outcome).toBe("unknown");
    expect(rows[5].outcome).toBe("running");
  });
});

describe("event captions", () => {
  it("says what happens and when", () => {
    expect(eventCaption({ type: "block_exit", exit_id: "door_s1", at_s: 60 }, names)).toBe("South door 1 blocked at 1:00");
    expect(eventCaption({ type: "surge", zone_id: "aud", extra_people: 1200, at_s: 30 }, names)).toBe("1,200 more people into Audience at 0:30");
    expect(eventCaption({ type: "slowdown", factor: 0.6, at_s: 0 }, names)).toBe("Everyone slows to 60% of their speed at 0:00");
    expect(eventCaption({ type: "marshal_redirect", to_exit_id: "door_e", at_s: 90 }, names)).toBe("Stewards send people to East door at 1:30");
    expect(eventCaption({ type: "flood", at_s: 5 }, names)).toBe("flood at 0:05");
  });
  it("orders an attack's events and a fix's steps on the timeline", () => {
    const a = attack("A1", "x", [{ type: "block_exit", exit_id: "door_s1", at_s: 60 }, { type: "surge", zone_id: "aud", extra_people: 10, at_s: 0 }] as Attack["events"]);
    const f = { operational: [{ type: "staggered_release", zone_id: "aud", delay_s: 45, at_s: 0 }] } as unknown as Fix;
    const m = scenarioMarkers(a, [f], names);
    expect(m.map((x) => [x.t, x.tone])).toEqual([[0, "caution"], [0, "egress"], [60, "danger"]]);
    expect(captionAt(m, 63)?.label).toBe("South door 1 blocked at 1:00");
    expect(captionAt(m, 75)).toBeNull();
    expect(captionAt([], 3)).toBeNull();
  });
});

describe("people per floor", () => {
  it("counts each floor's people per sampled frame", () => {
    // two frames: 3 people (2 on F1, 1 on F0), then 1 person on F0
    const frames = [[0, 1, 1], [0]];
    const sizes = frames.map((f) => { const b = 4 + f.length * 7; return b + ((4 - (b % 4)) % 4); });
    const buf = new ArrayBuffer(sizes.reduce((a, b) => a + b, 0));
    const offsets: number[] = [];
    let off = 0;
    frames.forEach((f, k) => {
      offsets.push(off);
      new DataView(buf).setUint32(off, f.length, true);
      new Uint8Array(buf, off + 4 + 6 * f.length, f.length).set(f);
      off += sizes[k];
    });
    const idx: TrajIndex = { format: "v1", times: [0, 10], offsets, bytes: buf.byteLength, origin: [0, 0], scale: 0.05,
      floors: ["F0", "F1"], bounds: [0, 0, 1, 1], max_agents: 3 };
    expect(peoplePerFloor(new Trajectory(idx, buf))).toEqual({ times: [0, 10], floors: ["F0", "F1"], counts: [[1, 1], [2, 0]] });
  });
});
