/** What changed between two venues, by object id: used to highlight a proposal in 3D. */
import type { Pt, Venue } from "@/api/types";

type ChangeKind = "added" | "changed" | "removed";

export interface ObjectChange {
  id: string;
  kind: ChangeKind;
  floorId: string;
  polygon: Pt[];
  what: "exit" | "obstacle" | "zone";
}

type Item = { id: string; polygon: unknown; floorId: string; what: ObjectChange["what"]; json: string };

function index(venue: Venue): Map<string, Item> {
  const out = new Map<string, Item>();
  for (const f of venue.floors) {
    const groups: [ObjectChange["what"], { id: string; polygon: unknown }[]][] = [["exit", f.exits], ["obstacle", f.obstacles], ["zone", f.zones]];
    for (const [what, items] of groups) {
      for (const it of items) out.set(it.id, { id: it.id, polygon: it.polygon, floorId: f.floor_id, what, json: JSON.stringify(it) });
    }
  }
  return out;
}

export function diffVenues(before: Venue, after: Venue): ObjectChange[] {
  const a = index(before);
  const b = index(after);
  const out: ObjectChange[] = [];
  for (const [id, it] of b) {
    const old = a.get(id);
    if (!old) out.push({ id, kind: "added", floorId: it.floorId, polygon: it.polygon as Pt[], what: it.what });
    else if (old.json !== it.json) out.push({ id, kind: "changed", floorId: it.floorId, polygon: it.polygon as Pt[], what: it.what });
  }
  for (const [id, it] of a) {
    if (!b.has(id)) out.push({ id, kind: "removed", floorId: it.floorId, polygon: it.polygon as Pt[], what: it.what });
  }
  return out;
}
