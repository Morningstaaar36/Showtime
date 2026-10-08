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

export interface Doorway {
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

/** Wall pieces along each outline edge, with door openings cut out. */
export function wallPieces(floor: Floor): { a: Pt; b: Pt; edge: Edge }[] {
  const doors = floor.exits.map((e) => doorwayOf(floor.walkable as Pt[], e)).filter((d): d is Doorway => !!d);
  const out: { a: Pt; b: Pt; edge: Edge }[] = [];
  for (const e of edgesOf(floor.walkable as Pt[])) {
    const cuts = doors
      .filter((d) => d.edge.a === e.a && d.edge.b === e.b)
      .map((d) => [Math.max(0, d.s - d.width / 2), Math.min(e.len, d.s + d.width / 2)] as [number, number])
      .sort((p, q) => p[0] - q[0]);
    let cursor = 0;
    for (const [s0, s1] of [...cuts, [e.len, e.len] as [number, number]]) {
      if (s0 - cursor > 0.05) {
        out.push({
          a: [e.a[0] + e.ux * cursor, e.a[1] + e.uy * cursor],
          b: [e.a[0] + e.ux * s0, e.a[1] + e.uy * s0],
          edge: e,
        });
      }
      cursor = Math.max(cursor, s1);
    }
  }
  return out;
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
