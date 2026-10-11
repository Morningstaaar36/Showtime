/** Organizer annotations on venue objects: provenance, locks, existing/proposed construction.
 *
 * Saved in venue extensions by the `set_annotation` patch op: provenance in `scene_metadata`
 * (the scene contract), locks and change status in `plan_annotations`. */
import type { InputProvenance, PatchOpIn, Venue } from "@/api/types";

export type Basis = InputProvenance["basis"];
export type ChangeStatus = "existing" | "proposed";
export const BASES: Basis[] = ["unknown", "assumed", "imported", "organizer_confirmed", "measured"];

export interface ObjectAnnotation {
  locked: boolean;
  /** null: never stated; templates and imports describe what is there */
  change: ChangeStatus | null;
  provenance: Partial<InputProvenance> & { basis: Basis };
}

type Entry = { locked?: boolean; change?: ChangeStatus };
type Section<T> = { objects?: Record<string, T> } | undefined;

function section<T>(venue: Venue, key: string): Record<string, T> {
  const ext = (venue.extensions ?? {}) as Record<string, unknown>;
  return (ext[key] as Section<T>)?.objects ?? {};
}

export function annotationOf(venue: Venue, id: string): ObjectAnnotation {
  const entry = section<Entry>(venue, "plan_annotations")[id] ?? {};
  const prov = section<Partial<InputProvenance>>(venue, "scene_metadata")[id];
  return {
    locked: entry.locked === true,
    change: entry.change ?? null,
    provenance: { ...prov, basis: (prov?.basis as Basis | undefined) ?? "unknown" },
  };
}

export function lockedIds(venue: Venue): Set<string> {
  const out = new Set<string>();
  for (const [id, e] of Object.entries(section<Entry>(venue, "plan_annotations"))) if (e.locked) out.add(id);
  return out;
}

export function isProposed(venue: Venue, id: string): boolean {
  return section<Entry>(venue, "plan_annotations")[id]?.change === "proposed";
}

/** The stage's obstacle id: `set_stage_param` edits it without naming it. */
function stageId(venue: Venue): string | null {
  for (const f of venue.floors) for (const o of f.obstacles) if (o.kind === "stage") return o.id;
  return null;
}

/** Ids of existing objects an operation changes (an added object is not "changed"). */
export function opTargets(op: PatchOpIn, venue: Venue): string[] {
  const o = op as Record<string, unknown>;
  const ids = ["target", "exit_id", "obstacle_id", "zone_id"].map((k) => o[k]).filter((v): v is string => typeof v === "string");
  if (o.op === "set_stage_param") {
    const s = stageId(venue);
    if (s) ids.push(s);
  }
  return ids;
}

export interface LockConflict { id: string; op: string }

/** Operations in a proposal that would change something the organizer locked. */
export function lockConflicts(venue: Venue, ops: PatchOpIn[]): LockConflict[] {
  const locked = lockedIds(venue);
  const out: LockConflict[] = [];
  for (const op of ops) {
    if (op.op === "set_annotation") continue; // the organizer's own lock changes
    for (const id of opTargets(op, venue)) if (locked.has(id)) out.push({ id, op: op.op });
  }
  return out;
}

/** A `set_annotation` op; only the fields given change. */
export function annotateOp(target: string, change: { locked?: boolean; change?: ChangeStatus; provenance?: Partial<InputProvenance> & { basis: Basis } }): PatchOpIn {
  return { op: "set_annotation", target, ...change } as PatchOpIn;
}
