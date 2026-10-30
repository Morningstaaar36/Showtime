/** A multi-storey building's outer skin: per storey a solid sill, a glazed window band with
 * mullions, and a solid spandrel up to the slab above; door openings keep their head and get a
 * glass transom. And a roof over each storey's part with nothing above it. Floor-relative. */
import * as THREE from "three";
import type { Floor, Pt, Venue } from "@/api/types";
import { edgesOf } from "../geom";
import { MeshBuilder } from "./builder";
import { DOOR_HEAD_M, type Run } from "./floor";
import { ccw, pointInRing, splitSegment, subtractConvex } from "./poly";

/** Top of the solid sill under the windows. */
export const SILL_M = 0.9;
/** Depth of the solid band (spandrel) between the window head and the slab above. */
const SPANDREL_M = 0.6;
/** Mullions stand about this far apart. */
const MULLION_EVERY_M = 2.4;
const GLASS_T = 0.04;
const MULLION_W = 0.07;
/** Parapet round a roof's edge. */
const PARAPET_M = 0.45;

export interface FacadeStyle {
  /** facade top (the slab above's underside) */
  height: number;
  thickness: number;
  doorHead?: number;
}

/** One side of the building (runs facing roughly the same way): the parts the live view drops on
 * the side nearest the camera, so the storey stays visible. */
export interface FacadeSide {
  /** outward normal, venue xy (unit) */
  normal: Pt;
  /** a point on the side (length-weighted middle of its runs) */
  mid: Pt;
  glass: THREE.BufferGeometry;
  spandrel: THREE.BufferGeometry;
  frame: THREE.BufferGeometry;
}

export interface Facade {
  /** the solid sill under the windows, all round (never cut away) */
  sill: THREE.BufferGeometry;
  sides: FacadeSide[];
  /** heights used: window band from `sill` to `windowTop`, spandrel from `windowTop` to the top */
  levels: { sill: number; windowTop: number; top: number };
}

/** The window band's heights for a storey `h` tall. */
export function facadeLevels(h: number): Facade["levels"] {
  const sill = Math.min(SILL_M, h * 0.3);
  const windowTop = Math.max(sill + 0.6, h - Math.min(SPANDREL_M, h * 0.2));
  return { sill, windowTop: Math.min(windowTop, h), top: h };
}

/** The facade over a storey's outer walls and door openings. With `bySide` the window band is
 * split into up to eight sides by the way they face (the live view cuts the near ones away);
 * without, everything is one side. Walls sit outside the walkable outline. */
export function facadeGeometry(edges: { walls: Run[]; doors: Run[] }, style: FacadeStyle, bySide = true): Facade {
  const { height: h, thickness: t } = style;
  const head = Math.min(style.doorHead ?? DOOR_HEAD_M, h);
  const lv = facadeLevels(h);
  const sill = new MeshBuilder();
  interface Acc { glass: MeshBuilder; spandrel: MeshBuilder; frame: MeshBuilder; nx: number; ny: number; mx: number; my: number; len: number }
  const groups = new Map<number, Acc>();
  const group = (r: Run): Acc => {
    const key = bySide ? ((Math.round(Math.atan2(r.edge.ny, r.edge.nx) / (Math.PI / 4)) % 8) + 8) % 8 : 0;
    let g = groups.get(key);
    if (!g) { g = { glass: new MeshBuilder(), spandrel: new MeshBuilder(), frame: new MeshBuilder(), nx: 0, ny: 0, mx: 0, my: 0, len: 0 }; groups.set(key, g); }
    const len = Math.hypot(r.b[0] - r.a[0], r.b[1] - r.a[1]);
    g.nx += r.edge.nx * len; g.ny += r.edge.ny * len;
    g.mx += (r.a[0] + r.b[0]) / 2 * len; g.my += (r.a[1] + r.b[1]) / 2 * len; g.len += len;
    return g;
  };
  const off = (r: Run): [Pt, Pt] => {
    const dx = r.edge.nx * t / 2, dy = r.edge.ny * t / 2;
    return [[r.a[0] + dx, r.a[1] + dy], [r.b[0] + dx, r.b[1] + dy]];
  };
  const mullions = (g: Acc, a: Pt, b: Pt, h0: number, h1: number) => {
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (len < 0.05 || h1 - h0 < 0.05) return;
    const ux = (b[0] - a[0]) / len, uy = (b[1] - a[1]) / len;
    const n = Math.max(1, Math.round(len / MULLION_EVERY_M));
    for (let i = 0; i <= n; i++) {
      const s = Math.min(len - MULLION_W / 2, Math.max(MULLION_W / 2, (len * i) / n));
      const p: Pt = [a[0] + ux * s, a[1] + uy * s];
      g.frame.beam([p[0] - ux * MULLION_W / 2, p[1] - uy * MULLION_W / 2], [p[0] + ux * MULLION_W / 2, p[1] + uy * MULLION_W / 2], t + 0.02, h0, h1);
    }
    // a slim transom at the window head and on the sill
    g.frame.beam(a, b, t + 0.02, h1 - 0.05, h1);
    g.frame.beam(a, b, t + 0.03, h0, h0 + 0.05);
  };
  for (const r of edges.walls) {
    const [a, b] = off(r);
    const g = group(r);
    sill.beam(a, b, t, 0, lv.sill, t / 2);
    g.glass.beam(a, b, GLASS_T, lv.sill, lv.windowTop);
    mullions(g, a, b, lv.sill, lv.windowTop);
    if (lv.top - lv.windowTop > 1e-3) g.spandrel.beam(a, b, t, lv.windowTop, lv.top, t / 2);
  }
  for (const r of edges.doors) {
    const [a, b] = off(r);
    const g = group(r);
    if (h - head <= 0.05) continue;
    // the door head, a glass transom over it when the window band reaches higher, the spandrel
    const lintelTop = Math.min(h, head + 0.15);
    g.spandrel.beam(a, b, t, head, lintelTop);
    if (lv.windowTop - lintelTop > 0.15) {
      g.glass.beam(a, b, GLASS_T, lintelTop, lv.windowTop);
      mullions(g, a, b, lintelTop, lv.windowTop);
      g.spandrel.beam(a, b, t, lv.windowTop, h);
    } else if (h - lintelTop > 1e-3) {
      g.spandrel.beam(a, b, t, lintelTop, h);
    }
  }
  const sides: FacadeSide[] = [...groups.values()].map((g) => {
    const n = Math.hypot(g.nx, g.ny) || 1;
    return { normal: [g.nx / n, g.ny / n], mid: [g.mx / (g.len || 1), g.my / (g.len || 1)],
      glass: g.glass.geometry(), spandrel: g.spandrel.geometry(), frame: g.frame.geometry() };
  });
  return { sill: sill.geometry(), sides, levels: lv };
}

/** Free a facade's geometries. */
export function disposeFacade(f: Facade): void {
  f.sill.dispose();
  for (const s of f.sides) { s.glass.dispose(); s.spandrel.dispose(); s.frame.dispose(); }
}

/** The floors whose plates stand higher than `floor` (they roof part of it over). */
function floorsAbove(venue: Venue, floor: Floor): Floor[] {
  const e = floor.elevation_m ?? 0;
  return venue.floors.filter((f) => (f.elevation_m ?? 0) > e + 0.01);
}

export interface Roof {
  /** the deck: top at `top`, `thickness` deep */
  deck: THREE.BufferGeometry;
  /** the deck's edge faces (a darker band) */
  band: THREE.BufferGeometry;
  /** a low parapet on top of the facade round the deck's outer edge */
  parapet: THREE.BufferGeometry;
}

/** The roof over the part of `floor` that no higher floor covers, its deck top at `top` (floor-
 * relative), `thickness` deep; null when every part has a floor above. */
export function roofGeometry(venue: Venue, floor: Floor, top: number, thickness: number, wallT: number): Roof | null {
  const ring = ccw(floor.walkable as Pt[]);
  if (ring.length < 3) return null;
  const covers = floorsAbove(venue, floor).map((f) => ccw(f.walkable as Pt[])).filter((r) => r.length >= 3);
  const coverTris = covers.flatMap((r) => THREE.ShapeUtils.triangulateShape(r.map(([x, y]) => new THREE.Vector2(x, y)), [])
    .map(([i, j, k]) => ccw([r[i], r[j], r[k]])));
  const deck = new MeshBuilder(), band = new MeshBuilder(), parapet = new MeshBuilder();
  const tris = THREE.ShapeUtils.triangulateShape(ring.map(([x, y]) => new THREE.Vector2(x, y)), []);
  let area = 0;
  for (const [i, j, k] of tris) {
    let pieces: Pt[][] = [[ring[i], ring[j], ring[k]]];
    for (const c of coverTris) pieces = pieces.flatMap((p) => subtractConvex(p, c));
    for (const p of pieces) {
      deck.flat(p, top, true).flat(p, top - thickness, false);
      for (let q = 1; q + 1 < p.length; q++) {
        area += Math.abs((p[q][0] - p[0][0]) * (p[q + 1][1] - p[0][1]) - (p[q + 1][0] - p[0][0]) * (p[q][1] - p[0][1])) / 2;
      }
    }
  }
  if (area < 0.5) return null;
  const open = (m: Pt) => !covers.some((c) => pointInRing(m, c));
  for (const e of edgesOf(ring)) {
    for (const [p, q] of splitSegment(e.a, e.b, covers, open)) {
      band.side(p, q, top - thickness, top, [e.nx, e.ny]);
      const dx = e.nx * wallT / 2, dy = e.ny * wallT / 2;
      parapet.beam([p[0] + dx, p[1] + dy], [q[0] + dx, q[1] + dy], wallT, top - thickness, top + PARAPET_M, wallT / 2);
    }
  }
  return { deck: deck.geometry(), band: band.geometry(), parapet: parapet.geometry() };
}
