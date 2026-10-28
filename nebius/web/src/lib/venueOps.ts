/** Payloads for the building-editor patch ops (floors, walls, doors, rooms, stairs, routes, people
 * profiles, event kind) and the geometry the editor needs to build them. Every builder returns a
 * `PatchOpIn` for POST /projects/{id}/patch, so undo, redo and versioning work as for other edits. */
import type { PatchOpIn, Pt, Venue } from "@/api/types";
import { t } from "@/i18n";
import type { EventKind, PeopleGroup } from "@/types/generated";

export type EventKindId = NonNullable<EventKind>;
export type PeopleKind = PeopleGroup["kind"];
export type Direction = "north" | "south" | "east" | "west";
export type Interior = "open" | "rooms";
type Floor = Venue["floors"][number];

export const EVENT_KINDS: EventKindId[] = [
  "concert", "festival", "conference", "wedding", "rally", "march", "sports", "religious",
  "hospital", "school", "office", "mall", "transit", "residential", "airport", "market", "campus", "other",
];
/** Groups the organizer can add to a zone; the rest of the headcount is general adults. */
export const GROUP_KINDS: Exclude<PeopleKind, "general">[] = ["elderly", "child", "wheelchair", "bed", "staff"];
export const DIRECTIONS: Direction[] = ["north", "east", "south", "west"];

// --- op payloads (the cross-stream contract, implemented by plugins/ops_core) ------------------

interface AddFloorOp { op: "add_floor"; floor_id?: string; name?: string; height_m?: number; copy_walls?: boolean }
interface RemoveFloorOp { op: "remove_floor"; floor_id: string }
interface AddStairOp {
  op: "add_stair"; id?: string; from_floor: string; to_floor: string; x: number; y: number;
  width_m?: number; run_m?: number; direction?: Direction;
}
interface RemoveStairOp { op: "remove_stair"; stair_id: string }
interface AddWallOp { op: "add_wall"; floor_id: string; id?: string; points: Pt[]; thickness_m?: number; height_m?: number }
interface AddDoorOp { op: "add_door"; floor_id: string; wall_id: string; x: number; y: number; width_m?: number }
interface AddRoomOp {
  op: "add_room"; floor_id: string; id?: string; x: number; y: number; width_m: number; depth_m: number;
  door_wall?: Direction; door_width_m?: number; people?: number; label?: string; groups?: PeopleGroup[];
}
interface SetZoneProfileOp {
  op: "set_zone_profile"; zone_id: string; groups?: PeopleGroup[]; pre_movement_s?: number | null; route_id?: string | null;
}
interface AddRouteOp { op: "add_route"; id?: string; floor_id: string; points: Pt[]; width_m?: number; label?: string }
interface RemoveRouteOp { op: "remove_route"; route_id: string }
interface SetEventKindOp { op: "set_event_kind"; event_kind: EventKindId | null }

type EditorOp = AddFloorOp | RemoveFloorOp | AddStairOp | RemoveStairOp | AddWallOp | AddDoorOp | AddRoomOp
  | SetZoneProfileOp | AddRouteOp | RemoveRouteOp | SetEventKindOp;

const asOp = (o: EditorOp): PatchOpIn => o as unknown as PatchOpIn;
const r2 = (v: number) => Math.round(v * 100) / 100;
const pt = (p: Pt): Pt => [r2(p[0]), r2(p[1])];

// --- floors ----------------------------------------------------------------------------------

/** Floors from the lowest to the highest. */
export function floorsByElevation(venue: Venue): Floor[] {
  return [...venue.floors].sort((a, b) => (a.elevation_m ?? 0) - (b.elevation_m ?? 0));
}

/** Storey numbers: 0 for the floor nearest elevation 0, then 1, 2… above it and −1, −2… below. */
export function floorLevels(venue: Venue): Map<string, number> {
  const sorted = floorsByElevation(venue);
  let ground = 0;
  sorted.forEach((f, i) => { if (Math.abs(f.elevation_m ?? 0) < Math.abs(sorted[ground].elevation_m ?? 0)) ground = i; });
  return new Map(sorted.map((f, i) => [f.floor_id, i - ground]));
}

/** A storey's name when it has none of its own: "Ground floor", "Floor 2", "Basement 1". */
export function levelName(level: number): string {
  if (level === 0) return t("editor.floor.ground");
  return level > 0 ? t("editor.floor.level_n", { n: level }) : t("editor.floor.basement_n", { n: -level });
}

/** The short tag on the floor switcher, as on a lift panel: "G", "2", "B1". */
export function levelTag(level: number): string {
  if (level === 0) return t("editor.floor.tag_ground");
  return level > 0 ? String(level) : t("editor.floor.tag_basement", { n: -level });
}

/** The floor tools act on: the chosen one when it still exists, else the ground (lowest) floor. */
export function resolveEditFloor(venue: Venue, editFloor: string | null): string {
  if (editFloor && venue.floors.some((f) => f.floor_id === editFloor)) return editFloor;
  return floorsByElevation(venue)[0].floor_id;
}

/** Next free `F<n>` id. */
export function nextFloorId(venue: Venue): string {
  const ids = new Set(venue.floors.map((f) => f.floor_id));
  let n = venue.floors.length;
  while (ids.has(`F${n}`)) n += 1;
  return `F${n}`;
}

/** Default name of the next storey ("Floor 1" on a one-storey building). */
export function nextFloorName(venue: Venue): string {
  return levelName(Math.max(...floorLevels(venue).values()) + 1);
}

/** A new storey above the current top one (the server places it `height_m` higher). */
export function addFloorOp(venue: Venue, opts: { name?: string; height_m?: number; copy_walls?: boolean } = {}): PatchOpIn {
  return asOp({
    op: "add_floor",
    floor_id: nextFloorId(venue),
    name: opts.name?.trim() || nextFloorName(venue),
    height_m: r2(opts.height_m ?? 3.5),
    copy_walls: opts.copy_walls ?? true,
  });
}

export const removeFloorOp = (floorId: string): PatchOpIn => asOp({ op: "remove_floor", floor_id: floorId });

// --- stairs ----------------------------------------------------------------------------------

/** Which floors a stair placed on `floorId` connects: down to the floor below, or (on the lowest
 * floor) up to the floor above. Null on a single-storey venue. */
export function stairEnds(venue: Venue, floorId: string): { from_floor: string; to_floor: string } | null {
  const sorted = floorsByElevation(venue);
  const i = sorted.findIndex((f) => f.floor_id === floorId);
  if (i < 0 || sorted.length < 2) return null;
  if (i > 0) return { from_floor: sorted[i].floor_id, to_floor: sorted[i - 1].floor_id };
  return { from_floor: sorted[1].floor_id, to_floor: sorted[0].floor_id };
}

export function addStairOp(venue: Venue, floorId: string, x: number, y: number,
  opts: { direction?: Direction; width_m?: number; run_m?: number; id?: string } = {}): PatchOpIn | null {
  const ends = stairEnds(venue, floorId);
  if (!ends) return null;
  const op: AddStairOp = {
    op: "add_stair", ...(opts.id ? { id: opts.id } : {}), ...ends, x: r2(x), y: r2(y),
    width_m: r2(opts.width_m ?? 1.5), run_m: r2(opts.run_m ?? 6), direction: opts.direction ?? "north",
  };
  return asOp(op);
}

export const removeStairOp = (stairId: string): PatchOpIn => asOp({ op: "remove_stair", stair_id: stairId });

// --- walls, doors, rooms ---------------------------------------------------------------------

/** Drops repeated points (a double-click adds the last point twice). */
export function cleanPolyline(points: Pt[], tol = 0.05): Pt[] {
  const out: Pt[] = [];
  for (const p of points) {
    const last = out[out.length - 1];
    if (!last || Math.hypot(p[0] - last[0], p[1] - last[1]) > tol) out.push(pt(p));
  }
  return out;
}

export function addWallOp(floorId: string, points: Pt[], opts: { id?: string; thickness_m?: number } = {}): PatchOpIn | null {
  const pts = cleanPolyline(points);
  if (pts.length < 2) return null;
  return asOp({ op: "add_wall", floor_id: floorId, ...(opts.id ? { id: opts.id } : {}), points: pts.slice(0, 50),
                thickness_m: r2(opts.thickness_m ?? 0.2) });
}

function closestOnSegment(p: Pt, a: Pt, b: Pt): { point: Pt; dist: number } {
  const [vx, vy] = [b[0] - a[0], b[1] - a[1]];
  const len2 = vx * vx + vy * vy;
  const t = len2 ? Math.max(0, Math.min(1, ((p[0] - a[0]) * vx + (p[1] - a[1]) * vy) / len2)) : 0;
  const q: Pt = [a[0] + vx * t, a[1] + vy * t];
  return { point: q, dist: Math.hypot(p[0] - q[0], p[1] - q[1]) };
}

function polylineLength(line: Pt[]): number {
  let n = 0;
  for (let i = 1; i < line.length; i++) n += Math.hypot(line[i][0] - line[i - 1][0], line[i][1] - line[i - 1][1]);
  return n;
}

interface WallHit { wallId: string; point: Pt; dist: number; length: number; segment: [Pt, Pt] }

/** Nearest inner wall (an obstacle of kind "wall" drawn as a line) to a point on a floor. */
export function nearestWall(floor: Floor, x: number, y: number): WallHit | null {
  let best: WallHit | null = null;
  for (const o of floor.obstacles) {
    if (o.kind !== "wall" || !o.line || o.line.length < 2) continue;
    const line = o.line as Pt[];
    for (let i = 1; i < line.length; i++) {
      const c = closestOnSegment([x, y], line[i - 1], line[i]);
      if (!best || c.dist < best.dist) best = { wallId: o.id, point: pt(c.point), dist: c.dist, length: polylineLength(line), segment: [line[i - 1], line[i]] };
    }
  }
  return best;
}

/** Distance to the venue's outer boundary (the walkable outline). */
function distanceToOutline(floor: Floor, x: number, y: number): number {
  const ring = floor.walkable as Pt[];
  let d = Infinity;
  for (let i = 0; i < ring.length; i++) d = Math.min(d, closestOnSegment([x, y], ring[i], ring[(i + 1) % ring.length]).dist);
  return d;
}

type DoorPlan = { op: PatchOpIn; at: Pt; wallId: string } | { error: "door_no_wall" | "door_outer_wall" | "door_wall_short" };

/** A door cut into the inner wall nearest the click (within `reach` metres). */
export function planDoor(floor: Floor, x: number, y: number, width = 1.0, reach = 1.5): DoorPlan {
  const hit = nearestWall(floor, x, y);
  if (!hit || hit.dist > reach) return { error: distanceToOutline(floor, x, y) <= reach ? "door_outer_wall" : "door_no_wall" };
  if (hit.length < width) return { error: "door_wall_short" };
  return {
    op: asOp({ op: "add_door", floor_id: floor.floor_id, wall_id: hit.wallId, x: hit.point[0], y: hit.point[1], width_m: r2(width) }),
    at: hit.point, wallId: hit.wallId,
  };
}

/** Snaps a point to nearby corners (outline, walls) and then onto the outline or a wall line. */
export function snapPoint(floor: Floor, x: number, y: number, tol = 0.6): Pt {
  const corners: Pt[] = [...(floor.walkable as Pt[])];
  const lines: Pt[][] = [[...(floor.walkable as Pt[]), (floor.walkable as Pt[])[0]]];
  for (const o of floor.obstacles) if (o.kind === "wall" && o.line && o.line.length >= 2) { corners.push(...(o.line as Pt[])); lines.push(o.line as Pt[]); }
  let best: Pt | null = null;
  let bd = tol;
  for (const c of corners) { const d = Math.hypot(c[0] - x, c[1] - y); if (d < bd) { bd = d; best = c; } }
  if (best) return pt(best);
  bd = tol / 2;
  for (const line of lines) {
    for (let i = 1; i < line.length; i++) {
      const c = closestOnSegment([x, y], line[i - 1], line[i]);
      if (c.dist < bd) { bd = c.dist; best = c.point; }
    }
  }
  return pt(best ?? [x, y]);
}

interface RoomSpec { x: number; y: number; width_m: number; depth_m: number }

/** A room from two opposite corners (any order): south-west corner plus size. */
export function roomFromCorners(a: Pt, b: Pt): RoomSpec {
  return { x: r2(Math.min(a[0], b[0])), y: r2(Math.min(a[1], b[1])), width_m: r2(Math.abs(b[0] - a[0])), depth_m: r2(Math.abs(b[1] - a[1])) };
}

export function roomOutline(r: RoomSpec): Pt[] {
  const corners: Pt[] = [[r.x, r.y], [r.x + r.width_m, r.y], [r.x + r.width_m, r.y + r.depth_m], [r.x, r.y + r.depth_m]];
  return corners.map(pt);
}

type RoomPlan = { op: PatchOpIn } | { error: "room_too_small" | "room_door_wide" };

export function planRoom(floorId: string, r: RoomSpec, opts: {
  door_wall?: Direction; door_width_m?: number; people?: number | null; label?: string; groups?: PeopleGroup[]; id?: string;
} = {}): RoomPlan {
  if (r.width_m < 1.5 || r.depth_m < 1.5) return { error: "room_too_small" };
  const side = opts.door_wall ?? "south";
  const door = opts.door_width_m ?? 1.0;
  if (door > (side === "north" || side === "south" ? r.width_m : r.depth_m) - 0.2) return { error: "room_door_wide" };
  const op: AddRoomOp = {
    op: "add_room", floor_id: floorId, ...(opts.id ? { id: opts.id } : {}), ...r, door_wall: side, door_width_m: r2(door),
    ...(opts.people != null && opts.people > 0 ? { people: Math.round(opts.people) } : {}),
    ...(opts.label?.trim() ? { label: opts.label.trim() } : {}),
    ...(opts.groups?.length ? { groups: opts.groups } : {}),
  };
  return { op: asOp(op) };
}

// --- people profile, routes, event kind --------------------------------------------------------

/** Rounds shares to whole percent; null when the shares are invalid (negative, or over 100% together). */
export function normalizeGroups(groups: PeopleGroup[]): PeopleGroup[] | null {
  const out: PeopleGroup[] = [];
  for (const g of groups) {
    if (!Number.isFinite(g.share) || g.share < 0 || g.share > 1) return null;
    const share = Math.round(g.share * 100) / 100;
    if (share > 0) out.push({ kind: g.kind, share });
  }
  const total = out.reduce((n, g) => n + g.share, 0);
  return total > 1.0001 ? null : out;
}

/** set_zone_profile with only the fields given; `null` clears pre-movement or the route. */
export function zoneProfileOp(zoneId: string, change: { groups?: PeopleGroup[]; pre_movement_s?: number | null; route_id?: string | null }): PatchOpIn {
  const op: SetZoneProfileOp = { op: "set_zone_profile", zone_id: zoneId };
  if (change.groups !== undefined) op.groups = change.groups;
  if (change.pre_movement_s !== undefined) op.pre_movement_s = change.pre_movement_s == null ? null : Math.round(change.pre_movement_s);
  if (change.route_id !== undefined) op.route_id = change.route_id;
  return asOp(op);
}

export function addRouteOp(floorId: string, points: Pt[], opts: { id?: string; width_m?: number | null; label?: string } = {}): PatchOpIn | null {
  const pts = cleanPolyline(points);
  if (pts.length < 2) return null;
  return asOp({
    op: "add_route", floor_id: floorId, ...(opts.id ? { id: opts.id } : {}), points: pts.slice(0, 200),
    ...(opts.width_m ? { width_m: r2(opts.width_m) } : {}), ...(opts.label?.trim() ? { label: opts.label.trim() } : {}),
  });
}

export const setEventKindOp = (kind: EventKindId | null): PatchOpIn => asOp({ op: "set_event_kind", event_kind: kind });

// --- map import ------------------------------------------------------------------------------

/** Building kinds that default to rooms inside (the server applies the same rule). */
const ROOMS_BY_DEFAULT = new Set<EventKindId>(["hospital", "school", "office", "residential"]);
export const defaultInterior = (use: EventKindId | null | undefined): Interior => (use && ROOMS_BY_DEFAULT.has(use) ? "rooms" : "open");

