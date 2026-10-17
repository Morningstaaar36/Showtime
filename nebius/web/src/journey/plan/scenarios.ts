/** "Every scenario the AI tested": the session's runs as rows an organizer can click to replay, the
 * scenario's events as timeline captions ("South door 1 blocked at 1:00"), and people per floor over
 * time. Pure: the page passes in the session view and names. */
import type { Attack, Fix } from "@/api/types";
import type { RunInfo, TreeNode } from "@/api/useSessionStream";
import { t } from "@/i18n";
import { runOutcome } from "@/lib/evidence";
import { fmtClock, fmtInt } from "@/lib/format";
import type { TimelineMarker } from "@/panels/Timeline";
import type { Trajectory } from "@/replay/trajectory";

export type Outcome = ReturnType<typeof runOutcome> | "running" | "failed";

export interface ScenarioRow {
  key: string;
  kind: TreeNode["kind"];
  title: string;
  runId: string;
  outcome: Outcome;
  evacS: number | null;
  peak: number | null;
  /** fix rows under an attack: kept or not */
  accepted?: boolean | null;
  attackId?: string | null;
  fixId?: string | null;
  children: ScenarioRow[];
}

function outcomeOf(node: TreeNode, run: RunInfo | undefined): Outcome {
  if (node.status === "pending" || node.status === "running") return "running";
  if (node.status === "failed") return "failed";
  return runOutcome(run);
}

const num = (v: number | null | undefined) => (typeof v === "number" && Number.isFinite(v) ? v : null);

/** Rows in the order things were tested: the plan as drawn, each attack with the fixes tried
 * against it, then the final before/after confirmation. Nodes without a run are left out. */
export function scenarioRows(nodes: Record<string, TreeNode>, runs: Record<string, RunInfo>,
  attacks: Attack[], fixes: Fix[], human: (s: string) => string = (s) => s): ScenarioRow[] {
  const row = (n: TreeNode, title: string): ScenarioRow => {
    const r = runs[n.run_id];
    const m = r?.metrics ?? n.metrics ?? {};
    return {
      key: n.node_id, kind: n.kind, title, runId: n.run_id, outcome: outcomeOf(n, r),
      evacS: num(m.evac_time_p95_s), peak: num(m.peak_density_ppm2), accepted: n.accepted ?? r?.accepted ?? null,
      attackId: n.attack_id ?? null, fixId: n.fix_id ?? null, children: [],
    };
  };
  const all = Object.values(nodes).filter((n) => n.run_id);
  const out: ScenarioRow[] = [];
  for (const n of all.filter((x) => x.kind === "baseline")) out.push(row(n, t("yourplan.sc_baseline")));
  const order = new Map(attacks.map((a, i) => [a.attack_id, i]));
  const atkNodes = all.filter((x) => x.kind === "attack")
    .sort((a, b) => (order.get(a.attack_id ?? "") ?? 99) - (order.get(b.attack_id ?? "") ?? 99));
  for (const n of atkNodes) {
    const a = attacks.find((x) => x.attack_id === n.attack_id);
    const title = human(a?.title ?? n.label);
    // the same attack re-run on the plan with the changes kept so far
    const r = row(n, n.node_id.includes(":current:") ? t("yourplan.sc_with_changes", { title }) : title);
    r.children = all.filter((x) => x.kind === "fix" && x.parent_id === n.node_id).map((f) => {
      const fix = fixes.find((x) => x.fix_id === f.fix_id);
      return row(f, human(fix?.title ?? f.label));
    });
    out.push(r);
  }
  for (const n of all.filter((x) => x.kind === "final")) {
    const a = attacks.find((x) => x.attack_id === n.attack_id);
    const title = human(a?.title ?? "");
    const after = n.node_id.endsWith(":after");
    out.push(row(n, t(after ? "yourplan.sc_final_after" : "yourplan.sc_final_before", { title })));
  }
  return out;
}

/** The row to show first: the worst attack that broke the plan, else the first row. */
export const firstRow = (rows: ScenarioRow[], worstAttackId: string | null | undefined): ScenarioRow | undefined =>
  rows.find((r) => r.kind === "attack" && r.attackId === worstAttackId) ?? rows[0];

type Ev = { type: string; at_s?: number; [k: string]: unknown };

/** One sentence per scenario event, with the time it happens. Unknown types still get a caption. */
export function eventCaption(ev: Ev, name: (id: string) => string): string {
  const at = fmtClock(ev.at_s ?? 0);
  const s = (k: string) => (typeof ev[k] === "string" ? name(ev[k] as string) : "");
  const n = (k: string) => (typeof ev[k] === "number" ? (ev[k] as number) : 0);
  switch (ev.type) {
    case "block_exit": return t("yourplan.ev_block", { exit: s("exit_id"), at });
    case "unblock_exit": return t("yourplan.ev_unblock", { exit: s("exit_id"), at });
    case "surge": return t("yourplan.ev_surge", { n: fmtInt(n("extra_people")), zone: s("zone_id"), at });
    case "slowdown": return t("yourplan.ev_slowdown", { p: Math.round(n("factor") * 100), at });
    case "counterflow": return t("yourplan.ev_counterflow", { n: fmtInt(n("people")), exit: s("exit_id"), at });
    case "staggered_release": return t("yourplan.ev_stagger", { zone: s("zone_id"), s: Math.round(n("delay_s")), at });
    case "marshal_redirect": return t("yourplan.ev_marshal", { exit: s("to_exit_id"), at });
    case "one_way": return t("yourplan.ev_one_way", { exit: s("exit_id"), at });
    case "script": return t("yourplan.ev_script", { title: typeof ev.title === "string" ? ev.title : "", at });
    default: return t("yourplan.ev_other", { what: ev.type.replace(/_/g, " "), at });
  }
}

const TONE: Record<string, TimelineMarker["tone"]> = {
  block_exit: "danger", surge: "caution", slowdown: "caution", counterflow: "caution", script: "caution",
  unblock_exit: "egress", staggered_release: "egress", marshal_redirect: "egress", one_way: "egress",
};

/** Timeline markers for a run: the attack's events, then the fixes' operational steps. */
export function scenarioMarkers(attack: Attack | undefined, fixes: Fix[], name: (id: string) => string): TimelineMarker[] {
  const evs = [...(attack?.events ?? []), ...fixes.flatMap((f) => f.operational ?? [])] as Ev[];
  return evs.map((e) => ({ t: e.at_s ?? 0, label: eventCaption(e, name), tone: TONE[e.type] ?? "signal" }))
    .sort((a, b) => a.t - b.t);
}

/** The caption to show at replay time `now`: the latest event in the last `holdS` seconds. */
export function captionAt(markers: TimelineMarker[], now: number, holdS = 8): TimelineMarker | null {
  let hit: TimelineMarker | null = null;
  for (const m of markers) if (m.t <= now && now - m.t <= holdS) hit = m;
  return hit;
}

export interface FloorSeries { times: number[]; floors: string[]; counts: number[][] }

/** People on each floor over time, sampled about `points` times across the replay. */
export function peoplePerFloor(traj: Trajectory, points = 120): FloorSeries {
  const floors = traj.index.floors;
  const total = traj.frameCount;
  const step = Math.max(1, Math.floor(total / points));
  const times: number[] = [];
  const counts: number[][] = floors.map(() => []);
  for (let k = 0; k < total; k += step) {
    const f = traj.frame(k);
    const c = new Array<number>(floors.length).fill(0);
    for (let i = 0; i < f.n; i++) if (f.floors[i] < c.length) c[f.floors[i]] += 1;
    times.push(traj.index.times[k]);
    c.forEach((v, j) => counts[j].push(v));
  }
  return { times, floors, counts };
}
