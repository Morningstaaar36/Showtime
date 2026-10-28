/** Drag and drop on the "Check your venue" screen: what a dropped palette item becomes and how a
 * dragged object moves, as patch ops. Pure functions so they are easy to test. */
import type { Exit, Floor, PatchOpIn, Pt, Venue } from "@/api/types";
import { t } from "@/i18n";
import { annotateOp, annotationOf, type ChangeStatus } from "@/lib/annotations";
import type { EditorDefaults } from "@/lib/editorDefaults";
import { centroid, edgesOf, exitRectAt, pointInPolygon } from "@/scene/geom";

export type PaletteItem = "door" | "fence" | "crowd" | "stall";
export type GrabKind = "exit" | "obstacle" | "zone" | "stage";

const SNAP = 0.5;

export interface Hit { floorId: string; x: number; y: number; inside: boolean }

/** Preview geometry of a palette item dropped at (x, y): a polygon, or two points for a fence. */
interface ItemShape { item: PaletteItem; points: Pt[] }

type Edge = ReturnType<typeof edgesOf>[number];

function distToSeg(x: number, y: number, e: Edge): number {
  const vx = e.b[0] - e.a[0], vy = e.b[1] - e.a[1];
  const len2 = vx * vx + vy * vy || 1;
  const t = Math.max(0, Math.min(1, ((x - e.a[0]) * vx + (y - e.a[1]) * vy) / len2));
  return Math.hypot(x - (e.a[0] + t * vx), y - (e.a[1] + t * vy));
}

function nearestEdge(walkable: Pt[], x: number, y: number): { edge: Edge; index: number } | null {
  const edges = edgesOf(walkable);
  let best: { edge: Edge; index: number; d: number } | null = null;
  for (let index = 0; index < edges.length; index++) {
    const d = distToSeg(x, y, edges[index]);
    if (!best || d < best.d) best = { edge: edges[index], index, d };
  }
  return best;
}

const square = (x: number, y: number, side: number): Pt[] => {
  const h = side / 2;
  const r = (v: number) => +v.toFixed(2);
  return [[r(x - h), r(y - h)], [r(x + h), r(y - h)], [r(x + h), r(y + h)], [r(x - h), r(y + h)]];
};
const allInside = (poly: Pt[], pts: Pt[]) => pts.every(([px, py]) => pointInPolygon(px, py, poly));

/** A door dropped anywhere on the floor goes to the closest point of the nearest outer wall long
 * enough for it, so it need not be aimed at a wall; null off the floor. */
function onNearestWall(walkable: Pt[], x: number, y: number, width: number): Pt[] | null {
  if (!pointInPolygon(x, y, walkable)) return null;
  let best: { px: number; py: number; d: number } | null = null;
  for (const e of edgesOf(walkable)) {
    if (e.len < width + 0.2) continue;
    const t = Math.max(0, Math.min(1, ((x - e.a[0]) * e.ux + (y - e.a[1]) * e.uy) / e.len));
    const px = e.a[0] + e.ux * e.len * t, py = e.a[1] + e.uy * e.len * t;
    const d = Math.hypot(x - px, y - py);
    if (!best || d < best.d) best = { px, py, d };
  }
  return best ? exitRectAt(walkable, best.px, best.py, width) : null;
}

/** Where the item would go; null when it does not fit there (a door off the floor, etc.). A door
 * is a new exit (`ed.exitWidth` wide); a crowd area holds `ed.crowdPeople` at the new-area
 * density, shrinking near walls (easy to change after). */
export function itemShape(floor: Floor, item: PaletteItem, x: number, y: number, ed: EditorDefaults): ItemShape | null {
  const walkable = floor.walkable as Pt[];
  if (item === "door") {
    const rect = exitRectAt(walkable, x, y, ed.exitWidth) ?? onNearestWall(walkable, x, y, ed.exitWidth);
    return rect ? { item, points: rect } : null;
  }
  if (!pointInPolygon(x, y, walkable)) return null;
  if (item === "fence") {
    const near = nearestEdge(walkable, x, y);
    const [ux, uy] = near ? [near.edge.ux, near.edge.uy] : [1, 0];
    for (const len of [8, 6, 4, 2]) {
      const h = len / 2;
      const pts: Pt[] = [[+(x - ux * h).toFixed(2), +(y - uy * h).toFixed(2)], [+(x + ux * h).toFixed(2), +(y + uy * h).toFixed(2)]];
      if (allInside(walkable, pts)) return { item, points: pts };
    }
    return null;
  }
  const sides = item === "crowd" ? [Math.sqrt(ed.crowdPeople / ed.zoneDensity), 8, 6, 4, 3] : [3, 2];
  for (const side of sides) {
    const sq = square(x, y, side);
    if (allInside(walkable, sq)) return { item, points: sq };
  }
  return null;
}

function wallName(walkable: Pt[], rect: Pt[]): string {
  const [cx, cy] = centroid(rect);
  const near = nearestEdge(walkable, cx, cy);
  if (!near) return t("check.new_name.new");
  const { nx, ny } = near.edge;
  return t(`check.new_name.${Math.abs(nx) >= Math.abs(ny) ? (nx > 0 ? "east" : "west") : (ny > 0 ? "north" : "south")}`);
}

/** "South door 3" when "South door 1" and "South door 2" exist; the plain name when it is the first. */
function freeName(venue: Venue, base: string): string {
  const labels = venue.floors.flatMap((f) => [...f.exits, ...f.obstacles, ...f.zones].map((o) => o.label ?? ""));
  const numbered = new RegExp(`^${base.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")} (\\d+)$`);
  let top = 0;
  for (const label of labels) {
    if (label === base) top = Math.max(top, 1);
    const m = numbered.exec(label);
    if (m) top = Math.max(top, Number(m[1]));
  }
  return top ? `${base} ${top + 1}` : base;
}

export interface Placement { ops: PatchOpIn[]; id: string; kind: GrabKind; name: string }

/** Patch ops for a palette item dropped at (x, y) on a floor, or an error message key. */
export function placeItem(venue: Venue, floorId: string, item: PaletteItem, x: number, y: number,
  change: ChangeStatus, newId: (prefix: string) => string, ed: EditorDefaults): Placement | { error: string } {
  const floor = venue.floors.find((f) => f.floor_id === floorId);
  if (!floor) return { error: "check.drop_on_venue" };
  const shape = itemShape(floor, item, x, y, ed);
  if (!shape) return { error: item === "door" ? "check.door_near_wall" : "check.drop_no_room" };
  const outdoor = venue.mode === "outdoor";
  if (item === "door") {
    const id = newId("exit");
    const name = freeName(venue, t(`check.new_name.${outdoor ? "gate" : "door"}`, { side: wallName(floor.walkable as Pt[], shape.points) }));
    return { id, kind: "exit", name, ops: [
      { op: "add_exit", floor_id: floorId, id, width_m: ed.exitWidth, polygon: shape.points, label: name } as PatchOpIn,
      annotateOp(id, { change }),
    ] };
  }
  if (item === "fence") {
    const id = newId("barrier");
    return { id, kind: "obstacle", name: t(`check.new_name.${outdoor ? "fence" : "barrier"}`), ops: [
      { op: "add_barrier_line", floor_id: floorId, id, points: shape.points, kind: outdoor ? "fence" : "barrier" } as PatchOpIn,
      annotateOp(id, { change }),
    ] };
  }
  if (item === "crowd") {
    const id = newId("zone");
    const name = freeName(venue, t("check.new_name.crowd"));
    return { id, kind: "zone", name, ops: [
      { op: "add_zone", floor_id: floorId, id, polygon: shape.points, people: ed.crowdPeople, label: name } as PatchOpIn,
    ] };
  }
  const id = newId("stall");
  const name = freeName(venue, t("check.new_name.stall"));
  return { id, kind: "obstacle", name, ops: [
    { op: "add_obstacle", floor_id: floorId, id, kind: "booth", polygon: shape.points, label: name } as PatchOpIn,
    annotateOp(id, { change }),
  ] };
}

const snap = (v: number) => Math.round(v / SNAP) * SNAP + 0; // + 0 turns -0 into 0

function findExit(venue: Venue, id: string): { exit: Exit; floor: Floor; index: number } | null {
  for (const floor of venue.floors) {
    const index = floor.exits.findIndex((e) => e.id === id);
    if (index >= 0) return { exit: floor.exits[index], floor, index };
  }
  return null;
}

export interface Move { ops: PatchOpIn[]; dx: number; dy: number; preview: Pt[] | null }

/** A door slides to where it is dropped on a wall; anything else moves by whole half metres. */
export function moveObject(venue: Venue, kind: GrabKind, id: string, start: [number, number], to: [number, number]): Move | { error: string } | null {
  if (kind === "exit") {
    const found = findExit(venue, id);
    if (!found) return null;
    const { exit, floor, index } = found;
    const walkable = floor.walkable as Pt[];
    const rect = exitRectAt(walkable, to[0], to[1], exit.width_m);
    if (!rect) return { error: "check.door_near_wall" };
    const [ox, oy] = centroid(exit.polygon as Pt[]);
    const [nx, ny] = centroid(rect);
    const dx = +(nx - ox).toFixed(2) + 0, dy = +(ny - oy).toFixed(2) + 0;
    if (Math.abs(dx) < 0.05 && Math.abs(dy) < 0.05) return null;
    const sameWall = nearestEdge(walkable, ox, oy)?.index === nearestEdge(walkable, nx, ny)?.index;
    if (sameWall) return { ops: [{ op: "move", target: id, dx, dy } as PatchOpIn], dx, dy, preview: rect };
    // another wall: the door turns, so it is replaced in place, keeping its name and what was recorded about it
    const a = annotationOf(venue, id);
    const ops: PatchOpIn[] = [
      { op: "remove_exit", exit_id: id } as PatchOpIn,
      { op: "add_exit", floor_id: floor.floor_id, id, width_m: exit.width_m, polygon: rect, label: exit.label ?? undefined, index } as PatchOpIn,
    ];
    if (a.change || a.provenance.basis !== "unknown") {
      ops.push(annotateOp(id, { ...(a.change ? { change: a.change } : {}), ...(a.provenance.basis !== "unknown" ? { provenance: a.provenance } : {}) }));
    }
    if (exit.blocked) ops.push({ op: "block_exit", exit_id: id, blocked: true } as PatchOpIn);
    return { ops, dx, dy, preview: rect };
  }
  const dx = snap(to[0] - start[0]), dy = snap(to[1] - start[1]);
  if (!dx && !dy) return null;
  return { ops: [{ op: "move", target: id, dx, dy } as PatchOpIn], dx, dy, preview: null };
}
