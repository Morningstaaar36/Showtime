import type { Venue } from "@/api/types";

/** Side of a floor an exit sits on (for naming exits that have no label). */
function sideOf(walkable: number[][], polygon: number[][]): string {
  const xs = walkable.map((p) => p[0]);
  const ys = walkable.map((p) => p[1]);
  const cx = polygon.reduce((a, p) => a + p[0], 0) / polygon.length;
  const cy = polygon.reduce((a, p) => a + p[1], 0) / polygon.length;
  const d: [number, string][] = [
    [cx - Math.min(...xs), "west"], [Math.max(...xs) - cx, "east"],
    [cy - Math.min(...ys), "south"], [Math.max(...ys) - cy, "north"],
  ];
  return d.sort((a, b) => a[0] - b[0])[0][1];
}

/** Name of one exit: its label, or "New east exit" for an exit added without one. */
export function exitName(floor: Venue["floors"][number], exit: Venue["floors"][number]["exits"][number]): string {
  return exit.label ?? `New ${sideOf(floor.walkable, exit.polygon)} exit`;
}

/** Readable names for exits, zones and objects: labels first; unlabelled exits by side. */
export function displayNames(venue: Venue): Map<string, string> {
  const map = new Map<string, string>();
  for (const f of venue.floors) {
    for (const e of f.exits) map.set(e.id, exitName(f, e));
    for (const z of f.zones) map.set(z.id, z.label ?? z.id);
    for (const o of f.obstacles) map.set(o.id, o.label ?? o.kind.replace(/_/g, " "));
  }
  return map;
}

/**
 * Replace machine ids in model-written text ("street_w", "door_e1") with the names shown in 3D.
 * Only ids with "_" or a digit are replaced, so ordinary words that double as ids stay untouched.
 */
export function textHumanizer(venue: Venue): (text: string) => string {
  const map = new Map<string, string>();
  for (const [id, name] of displayNames(venue)) if (name !== id && /[_\d]/.test(id)) map.set(id, name);
  for (const st of venue.stairs ?? []) if (/[_\d]/.test(st.id)) map.set(st.id, "the stairs");
  if (!map.size) return (t) => t;
  const ids = [...map.keys()].sort((a, b) => b.length - a.length).map((id) => id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(`\\b(${ids.join("|")})\\b`, "g");
  return (text) => text.replace(re, (m) => map.get(m) ?? m);
}
