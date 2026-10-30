/** Geometry helpers. Venue coordinates (x east, y north, metres) map to three.js as
 *  world.x = x, world.z = -y, world.y = elevation. */
import * as THREE from "three";
import type { Exit, Floor, Pt, Venue } from "@/api/types";

export const WALL_INDOOR_M = 2.4; // cut-away height so the interior stays visible
export const FENCE_M = 1.15;
export const WALL_T = 0.18;

export function w(x: number, y: number, elev = 0): THREE.Vector3 {
  return new THREE.Vector3(x, elev, -y);
}

/** THREE.Shape in venue XY; after rotateX(-PI/2) the shape lies on the floor in world space. */
export function shapeOf(points: Pt[] | number[][]): THREE.Shape {
  const s = new THREE.Shape();
  points.forEach((p, i) => (i === 0 ? s.moveTo(p[0], p[1]) : s.lineTo(p[0], p[1])));
  s.closePath();
  return s;
}

export function bbox(points: Pt[] | number[][]): [number, number, number, number] {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const p of points) {
    x0 = Math.min(x0, p[0]); y0 = Math.min(y0, p[1]);
    x1 = Math.max(x1, p[0]); y1 = Math.max(y1, p[1]);
  }
  return [x0, y0, x1, y1];
}

export function centroid(points: Pt[] | number[][]): [number, number] {
  let a = 0, cx = 0, cy = 0;
  for (let i = 0; i < points.length; i++) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[(i + 1) % points.length];
    const c = x0 * y1 - x1 * y0;
    a += c; cx += (x0 + x1) * c; cy += (y0 + y1) * c;
  }
  if (Math.abs(a) < 1e-9) {
    const [bx0, by0, bx1, by1] = bbox(points);
    return [(bx0 + bx1) / 2, (by0 + by1) / 2];
  }
  return [cx / (3 * a), cy / (3 * a)];
}

export function polygonArea(points: Pt[] | number[][]): number {
  let a = 0;
  for (let i = 0; i < points.length; i++) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[(i + 1) % points.length];
    a += x0 * y1 - x1 * y0;
  }
  return Math.abs(a) / 2;
}

export function pointInPolygon(x: number, y: number, poly: Pt[] | number[][]): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function distToSeg(px: number, py: number, ax: number, ay: number, bx: number, by: number): [number, number] {
  const dx = bx - ax, dy = by - ay;
  const len2 = dx * dx + dy * dy || 1e-9;
  const t = Math.max(0, Math.min(1, ((px - ax) * dx + (py - ay) * dy) / len2));
  const qx = ax + t * dx, qy = ay + t * dy;
  return [Math.hypot(px - qx, py - qy), t];
}

export interface Edge {
  a: Pt;
  b: Pt;
  len: number;
  ux: number;
  uy: number;
  /** outward normal (pointing out of the walkable area) */
  nx: number;
  ny: number;
}

export function edgesOf(poly: Pt[] | number[][]): Edge[] {
  const pts = poly as Pt[];
  const out: Edge[] = [];
  // orientation: positive area = counter-clockwise -> outward normal is (uy, -ux)
  let area = 0;
  for (let i = 0; i < pts.length; i++) {
    const [x0, y0] = pts[i];
    const [x1, y1] = pts[(i + 1) % pts.length];
    area += x0 * y1 - x1 * y0;
  }
  const ccw = area > 0;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % pts.length];
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (len < 1e-6) continue;
    const ux = (b[0] - a[0]) / len, uy = (b[1] - a[1]) / len;
    const nx = ccw ? uy : -uy, ny = ccw ? -ux : ux;
    out.push({ a, b, len, ux, uy, nx, ny });
  }
  return out;
}

interface Doorway {
  edge: Edge;
  /** centre of the opening on the wall line */
  cx: number;
  cy: number;
  /** distance along the edge of the opening's centre */
  s: number;
  width: number;
}

/** Where an exit sits on the outline (nearest edge), or null if it is not on a wall. */
export function doorwayOf(walkable: Pt[] | number[][], exit: Exit): Doorway | null {
  const [cx, cy] = centroid(exit.polygon as Pt[]);
  let best: { e: Edge; d: number; t: number } | null = null;
  for (const e of edgesOf(walkable)) {
    const [d, t] = distToSeg(cx, cy, e.a[0], e.a[1], e.b[0], e.b[1]);
    if (!best || d < best.d) best = { e, d, t };
  }
  if (!best || best.d > 0.9) return null;
  const s = best.t * best.e.len;
  return { edge: best.e, cx: best.e.a[0] + best.e.ux * s, cy: best.e.a[1] + best.e.uy * s, s,
           width: exit.width_m };
}

/** Exit rectangle (0.4 m deep, inside the outline) for a click at (x, y) near a wall. */
export function exitRectAt(walkable: Pt[] | number[][], x: number, y: number, width: number): Pt[] | null {
  let best: { e: Edge; d: number; t: number } | null = null;
  for (const e of edgesOf(walkable)) {
    const [d, t] = distToSeg(x, y, e.a[0], e.a[1], e.b[0], e.b[1]);
    if (!best || d < best.d) best = { e, d, t };
  }
  if (!best || best.d > 3 || best.e.len < width + 0.2) return null;
  const e = best.e;
  const s = Math.min(Math.max(best.t * e.len, width / 2 + 0.1), e.len - width / 2 - 0.1);
  const cx = e.a[0] + e.ux * s, cy = e.a[1] + e.uy * s;
  const inset = 0.02, depth = 0.4;
  const ix = -e.nx, iy = -e.ny; // inward
  const h = width / 2;
  const p = (along: number, inw: number): Pt => [
    +(cx + e.ux * along + ix * inw).toFixed(3),
    +(cy + e.uy * along + iy * inw).toFixed(3),
  ];
  return [p(-h, inset), p(h, inset), p(h, inset + depth), p(-h, inset + depth)];
}

/** Bounds of the whole venue (all floors). */
export function venueBounds(v: Venue): [number, number, number, number] {
  return bbox(v.floors.flatMap((f) => f.walkable as Pt[]));
}

/** World Y of a floor (exploded view spreads floors apart). */
export function floorY(v: Venue, floorId: string, exploded: boolean): number {
  const sorted = [...v.floors].sort((a, b) => (a.elevation_m ?? 0) - (b.elevation_m ?? 0));
  const idx = sorted.findIndex((f) => f.floor_id === floorId);
  const elev = v.floors.find((f) => f.floor_id === floorId)?.elevation_m ?? 0;
  return exploded ? elev * 1.6 + idx * 6 : elev;
}

// --- floor view ------------------------------------------------------------------------------

/** Floors bottom to top. */
export function floorsBottomUp(v: Venue): Floor[] {
  return [...v.floors].sort((a, b) => (a.elevation_m ?? 0) - (b.elevation_m ?? 0));
}

/** From this many storeys up, the 3D view opens on one floor with the others ghosted: every room
 * wall of four floors at once reads as a stack of ribbed slabs. */
export const FOCUS_FROM = 3;

/** The floor view the scene can draw: an unknown floor id (another venue's) falls back to all;
 * "auto" (the default) focuses the lowest floor of a building with {@link FOCUS_FROM} storeys. */
export function resolveFloorView(v: Venue, view: string | null | undefined): string {
  if (!view || view === "auto") return v.floors.length >= FOCUS_FROM ? floorsBottomUp(v)[0].floor_id : "all";
  if (view === "all") return "all";
  if (view === "exploded") return v.floors.length > 1 ? "exploded" : "all";
  return v.floors.some((f) => f.floor_id === view) ? view : "all";
}

/** Bounds of one floor's walkable area. */
export function floorBounds(v: Venue, floorId: string): [number, number, number, number] {
  const f = v.floors.find((x) => x.floor_id === floorId);
  return f ? bbox(f.walkable as Pt[]) : venueBounds(v);
}

// --- stairs ----------------------------------------------------------------------------------

interface StairRun {
  /** foot of the stair (lower floor) and head (upper floor), venue metres */
  bx: number;
  by: number;
  tx: number;
  ty: number;
  run: number;
  /** heading of the climb, radians from +x (east) */
  angle: number;
}

/** Steepest pitch (rise over run) drawn as a flight between the landings' facing edges. */
const MAX_FLIGHT_PITCH = 0.9;

/** Where a stair climbs. The flight runs from the bottom landing's edge facing the top landing to
 * the top landing's edge facing the bottom one, so the landings stay level floor; when that gap is
 * too short for a walkable pitch (landings drawn as parts of one stair footprint) it runs centre
 * to centre. When both landings sit on the same footprint (a stairwell drawn as one box), the
 * climb runs along the footprint's long side. `rise` is the height the flight climbs. */
export function stairRun(top: Pt[] | number[][], bottom: Pt[] | number[][], rise = 0): StairRun {
  const [tx, ty] = centroid(top);
  const [bx, by] = centroid(bottom);
  const d = Math.hypot(tx - bx, ty - by);
  if (d >= 0.5) {
    const ux = (tx - bx) / d, uy = (ty - by) / d;
    const along = (p: number[]) => (p[0] - bx) * ux + (p[1] - by) * uy;
    const foot = Math.max(...bottom.map(along));
    const head = Math.min(...top.map(along));
    const gap = head - foot;
    if (rise > 0.3 && gap >= 0.5 && rise / gap <= MAX_FLIGHT_PITCH) {
      return { bx: bx + ux * foot, by: by + uy * foot, tx: bx + ux * head, ty: by + uy * head, run: gap, angle: Math.atan2(uy, ux) };
    }
    return { bx, by, tx, ty, run: d, angle: Math.atan2(ty - by, tx - bx) };
  }
  const [x0, y0, x1, y1] = bbox(top);
  const alongX = x1 - x0 >= y1 - y0;
  const run = Math.max(alongX ? x1 - x0 : y1 - y0, 1);
  const cx = (tx + bx) / 2, cy = (ty + by) / 2;
  return alongX
    ? { bx: cx - run / 2, by: cy, tx: cx + run / 2, ty: cy, run, angle: 0 }
    : { bx: cx, by: cy - run / 2, tx: cx, ty: cy + run / 2, run, angle: Math.PI / 2 };
}

/** Side profile of a stair (x along the run, y up) as a closed outline: steps on top, a straight
 * soffit underneath. A stair between floors at the same level is a flat landing. */
export function stairProfile(run: number, rise: number, riserM = 0.18): Pt[] {
  if (rise <= 0.3) return [[0, -0.15], [run, -0.15], [run, 0.02], [0, 0.02]];
  const n = Math.max(4, Math.min(60, Math.round(rise / riserM)));
  const d = run / n, s = rise / n;
  const pts: Pt[] = [[0, 0]];
  for (let i = 0; i < n; i++) {
    pts.push([i * d, (i + 1) * s]);
    pts.push([(i + 1) * d, (i + 1) * s]);
  }
  pts.push([run, rise - Math.min(0.35, rise * 0.25)]);
  return pts;
}

// --- walls drawn as lines --------------------------------------------------------------------

export function polylineLength(points: Pt[] | number[][]): number {
  let len = 0;
  for (let i = 1; i < points.length; i++) len += Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]);
  return len;
}

/** Thickness of a wall drawn along a centreline: its footprint area over its length. */
export function wallThickness(polygon: Pt[] | number[][], line: Pt[] | number[][]): number {
  const len = polylineLength(line);
  if (len < 1e-6) return WALL_T;
  return Math.max(0.08, Math.min(0.6, polygonArea(polygon) / len));
}

// --- routes ----------------------------------------------------------------------------------

/** Chevron positions along a route, every `spacing` metres, pointing in walking order. */
export function routeMarks(points: Pt[] | number[][], spacing: number): { x: number; y: number; angle: number }[] {
  const out: { x: number; y: number; angle: number }[] = [];
  if (points.length < 2 || spacing <= 0) return out;
  let next = spacing / 2;
  let walked = 0;
  for (let i = 1; i < points.length; i++) {
    const [ax, ay] = points[i - 1];
    const [bx, by] = points[i];
    const len = Math.hypot(bx - ax, by - ay);
    if (len < 1e-6) continue;
    const angle = Math.atan2(by - ay, bx - ax);
    while (next <= walked + len && out.length < 2000) {
      const k = (next - walked) / len;
      out.push({ x: ax + (bx - ax) * k, y: ay + (by - ay) * k, angle });
      next += spacing;
    }
    walked += len;
  }
  return out;
}
