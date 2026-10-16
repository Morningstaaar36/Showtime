/** Who is in a crowd area and when they start moving: the editor's draft of a zone's people mix,
 * and the ops that save it. Shares are edited as whole percents and saved as 0–1. */
import type { PatchOpIn, Venue } from "@/api/types";
import type { PeopleGroup } from "@/types/generated";
import type { EventKindInfo } from "./eventKinds";
import { GROUP_KINDS, normalizeGroups, type PeopleKind, zoneProfileOp } from "./venueOps";

export interface GroupRow { kind: Exclude<PeopleKind, "general">; percent: string }

export const rowsOf = (groups: PeopleGroup[] | null | undefined): GroupRow[] =>
  (groups ?? []).filter((g): g is PeopleGroup & { kind: GroupRow["kind"] } => g.kind !== "general" && g.share > 0)
    .map((g) => ({ kind: g.kind, percent: String(Math.round(g.share * 100)) }));

/** Kinds not yet in the list, in the editor's order. */
export const kindsLeft = (rows: GroupRow[]): GroupRow["kind"][] => GROUP_KINDS.filter((k) => !rows.some((r) => r.kind === k));

/** The rows as groups, or why they cannot be saved. */
export function groupsOf(rows: GroupRow[]): { groups: PeopleGroup[] } | { error: "over" | "invalid" } {
  const raw: PeopleGroup[] = [];
  for (const r of rows) {
    const n = Number(r.percent);
    if (r.percent.trim() === "" || !Number.isFinite(n) || n < 0 || n > 100) return { error: "invalid" };
    raw.push({ kind: r.kind, share: n / 100 });
  }
  const groups = normalizeGroups(raw);
  return groups ? { groups } : { error: "over" };
}

/** Percent of general adults left once the rows are counted (never below 0). */
export function restPercent(rows: GroupRow[]): number {
  const used = rows.reduce((n, r) => n + (Number.isFinite(Number(r.percent)) ? Number(r.percent) : 0), 0);
  return Math.max(0, Math.round(100 - used));
}

const sameGroups = (a: PeopleGroup[] | null | undefined, b: PeopleGroup[]) =>
  JSON.stringify((a ?? []).map((g) => [g.kind, g.share])) === JSON.stringify(b.map((g) => [g.kind, g.share]));

/** "Use the usual people mix in every area": one set_zone_profile per crowd area that has people
 * and differs from the usual mix (and the usual start delay, when one is cited). */
export function usualMixOps(venue: Venue, kind: EventKindInfo): PatchOpIn[] {
  if (!kind.default_groups.length && kind.default_pre_movement_s == null) return [];
  const ops: PatchOpIn[] = [];
  for (const f of venue.floors) {
    for (const z of f.zones) {
      if (z.people <= 0) continue;
      const change: { groups?: PeopleGroup[]; pre_movement_s?: number } = {};
      if (kind.default_groups.length && !sameGroups(z.groups, kind.default_groups)) change.groups = kind.default_groups;
      if (kind.default_pre_movement_s != null && z.pre_movement_s !== kind.default_pre_movement_s) change.pre_movement_s = kind.default_pre_movement_s;
      if (Object.keys(change).length) ops.push(zoneProfileOp(z.id, change));
    }
  }
  return ops;
}

/** Routes a crowd on `floorId` can walk. */
export const routesOn = (venue: Venue, floorId: string) => (venue.routes ?? []).filter((r) => r.floor_id === floorId);
