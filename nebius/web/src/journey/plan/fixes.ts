/** Choosing among the tested fixes on Your plan (P3-03): where each one came from, which
 * earlier fixes it builds on, what its own test showed, and what "Accept these changes" sends. */
import type { Fix, PatchOpIn } from "@/api/types";
import { t } from "@/i18n";
import { fmtDuration } from "@/lib/format";

export type FixSource = "ai" | "rules";

/** Standard engineering responses are tagged by the rules; everything else is the AI's idea. */
export function fixSource(fix: Fix): FixSource {
  return (fix.extensions as Record<string, unknown> | undefined)?.generated_by === "rules" ? "rules" : "ai";
}

const CREATES = new Set(["add_exit", "add_obstacle", "add_barrier_line", "add_zone"]);
const REFS = ["target", "exit_id", "zone_id", "obstacle_id", "from_exit_id", "to_exit_id", "target_zone_id"] as const;

/** Ids a fix brings into the plan: new exits, barriers and zones, and new staffed actions. */
export function createdIds(fix: Fix): Set<string> {
  const out = new Set<string>();
  for (const o of (fix.patch?.ops ?? []) as PatchOpIn[]) if (CREATES.has(o.op) && typeof o.id === "string") out.add(o.id);
  for (const id of Object.keys(fix.new_objects ?? {})) out.add(id);
  for (const a of fix.actions ?? []) out.add(a.action_id);
  return out;
}

/** Ids a fix refers to, in its edits, measures and staffed actions. */
export function referencedIds(fix: Fix): Set<string> {
  const out = new Set<string>();
  const add = (rec: Record<string, unknown> | null | undefined) => {
    for (const k of REFS) {
      const v = rec?.[k];
      if (typeof v === "string") out.add(v);
    }
  };
  for (const o of (fix.patch?.ops ?? []) as PatchOpIn[]) add(o);
  for (const e of fix.operational ?? []) add(e as Record<string, unknown>);
  for (const a of fix.actions ?? []) {
    add(a.event as Record<string, unknown> | null | undefined);
    for (const id of [...(a.target_ids ?? []), ...(a.depends_on ?? [])]) out.add(id);
  }
  for (const a of fix.replace_actions ?? []) {
    out.add(a.action_id);
    add(a.event as Record<string, unknown> | null | undefined);
    for (const id of [...(a.target_ids ?? []), ...(a.depends_on ?? [])]) out.add(id);
  }
  for (const id of fix.remove_action_ids ?? []) out.add(id);
  return out;
}

/** For each kept fix (in kept order), the earlier kept fixes it builds on: marshals sending
 * people to a door that another fix adds cannot be applied without that door. */
export function fixDependencies(kept: Fix[]): Record<string, string[]> {
  const deps: Record<string, string[]> = {};
  kept.forEach((fix, i) => {
    const refs = referencedIds(fix);
    deps[fix.fix_id] = kept.slice(0, i)
      .filter((prev) => [...createdIds(prev)].some((id) => refs.has(id)))
      .map((prev) => prev.fix_id);
  });
  return deps;
}

/** Tick or untick one fix and keep the choice buildable: a fix comes with the fixes it builds
 * on, and leaving a fix out also leaves out the fixes that build on it. */
export function toggleFix(selected: ReadonlySet<string>, id: string, deps: Record<string, string[]>): Set<string> {
  const next = new Set(selected);
  if (next.has(id)) {
    const drop = (x: string) => {
      next.delete(x);
      for (const [fid, needs] of Object.entries(deps)) if (needs.includes(x) && next.has(fid)) drop(fid);
    };
    drop(id);
  } else {
    const add = (x: string) => {
      next.add(x);
      for (const need of deps[x] ?? []) if (!next.has(need)) add(need);
    };
    add(id);
  }
  return next;
}

/** Every kept fix chosen: the plan that was tested together. */
export function testedTogether(selected: ReadonlySet<string>, keptIds: string[]): boolean {
  return keptIds.length > 0 && keptIds.every((id) => selected.has(id));
}

/** What "Accept these changes" sends: nothing extra for every kept fix (the venue tested
 * together), else the chosen ids in the order the session kept them. */
export function acceptBody(selected: ReadonlySet<string>, keptIds: string[]): { fix_ids?: string[] } {
  return testedTogether(selected, keptIds) ? {} : { fix_ids: keptIds.filter((id) => selected.has(id)) };
}

/** A session branch node as the stream reports it (`branch_node` events, merged). */
export interface NodeLike {
  run_id?: string;
  status?: string;
  basis?: string | null;
  tier?: number;
  fallback_for?: string | null;
  metrics?: Record<string, number | null>;
}

export interface FixTest {
  attackId: string;
  before: NodeLike | null;
  after: NodeLike | null;
}

/** A kept fix's own test: its attack on the venue with the fixes kept before it (re-run when
 * an earlier fix of the round was kept), then the same attack with the fix. */
export function fixTest(fix: Fix, keptIndex: number, nodes: Record<string, NodeLike | undefined>): FixTest {
  const a = fix.for_attack;
  return {
    attackId: a,
    before: nodes[`atk:${a}:current:${keptIndex}`] ?? nodes[`atk:${a}`] ?? null,
    after: nodes[`fix:${fix.fix_id}`] ?? null,
  };
}

/** Evacuation time (95%) of headline metrics; a time-capped run's extrapolation says so. */
export function evacValue(m: Record<string, number | null | undefined> | null | undefined): string {
  if (!m) return "–";
  if (m.evac_time_p95_s != null) return fmtDuration(m.evac_time_p95_s);
  if (m.evac_time_estimate_s != null) return t("yourplan.about", { d: fmtDuration(m.evac_time_estimate_s) });
  return t("yourplan.not_reached");
}
