/** One storey as built things: outer walls with door openings (a lintel over each door), guard
 * rails along open edges (a mezzanine's front, a stairwell's sides) and columns under them. */
import * as THREE from "three";
import type { Floor, Pt, Venue } from "@/api/types";
import { doorwayOf, edgesOf, type Edge } from "../geom";
import { MeshBuilder } from "./builder";
import { ccw, insideConvex, pointInRing, segDist, splitSegment } from "./poly";
import { flightFeet, flightFootprint, stairOpenings, stairPlacement } from "./stairs";

/** Top of a door opening; the gate frame fits under it. */
export const DOOR_HEAD_M = 2.1;
const GUARD_RAIL_M = 1.1;
/** An upper floor's edge within this of the outline below sits over an outer wall. */
const OVER_WALL_M = 0.5;

export interface Run {
  a: Pt;
  b: Pt;
  edge: Edge;
}

interface OuterEdges {
  /** solid outer wall */
  walls: Run[];
  /** door openings in the outer wall (a lintel goes over each) */
  doors: Run[];
  /** open edges (over the room below, or overhanging): a guard rail */
  open: Run[];
}

/** The storey under this one (highest elevation below it), or null for the lowest. */
export function floorBelow(venue: Venue, floor: Floor): Floor | null {
  const e = floor.elevation_m ?? 0;
  let best: Floor | null = null;
  for (const f of venue.floors) {
    const fe = f.elevation_m ?? 0;
    if (fe < e - 0.01 && (!best || fe > (best.elevation_m ?? 0))) best = f;
  }
  return best;
}

/** Split the floor's outline into outer wall, door openings and open edges. Every edge of the
 * lowest floor is wall; an upper floor's edge is wall where it sits over the outline below. */
export function outerEdges(floor: Floor, below: Floor | null): OuterEdges {
  const out: OuterEdges = { walls: [], doors: [], open: [] };
  const walk = floor.walkable as Pt[];
  const doors = floor.exits.map((e) => doorwayOf(walk, e)).filter((d) => !!d);
  const lower = below ? edgesOf(ccw(below.walkable as Pt[])) : null;
  // over a wall: a parallel edge of the outline below runs within OVER_WALL_M
  const overWall = (m: Pt, e: Edge) => !lower || lower.some((l) => Math.abs(l.ux * e.uy - l.uy * e.ux) < 0.1 && segDist(m, l.a, l.b) <= OVER_WALL_M);
  for (const e of edgesOf(walk)) {
    const at = (s: number): Pt => [e.a[0] + e.ux * s, e.a[1] + e.uy * s];
    const cuts = doors.filter((d) => d.edge.a === e.a && d.edge.b === e.b)
      .map((d) => [Math.max(0, d.s - d.width / 2), Math.min(e.len, d.s + d.width / 2)] as [number, number])
      .sort((p, q) => p[0] - q[0]);
    // wall / open runs along the edge, sampled every 0.5 m
    const runs: [number, number, boolean][] = [];
    const n = Math.max(1, Math.ceil(e.len / 0.5));
    for (let i = 0; i < n; i++) {
      const s0 = (e.len * i) / n, s1 = (e.len * (i + 1)) / n;
      const wall = overWall(at((s0 + s1) / 2), e);
      const last = runs[runs.length - 1];
      if (last && last[2] === wall) last[1] = s1;
      else runs.push([s0, s1, wall]);
    }
    for (const [r0, r1, wall] of runs) {
      let cursor = r0;
      const push = (list: Run[], s0: number, s1: number) => { if (s1 - s0 > 0.05) list.push({ a: at(s0), b: at(s1), edge: e }); };
      for (const [c0, c1] of cuts) {
        if (c1 <= r0 || c0 >= r1) continue;
        push(wall ? out.walls : out.open, cursor, Math.max(cursor, c0));
        if (wall) push(out.doors, Math.max(r0, c0), Math.min(r1, c1));
        cursor = Math.max(cursor, Math.min(r1, c1));
      }
      push(wall ? out.walls : out.open, cursor, r1);
    }
  }
  return out;
}

interface WallStyle {
  height: number;
  thickness: number;
  /** a dark section-cut strip on top of the walls (the plan-drawing cut) */
  cap?: boolean;
  /** door head height; no lintel when the wall is lower than this */
  doorHead?: number;
}

/** Outer walls as one merged body (lintels over doors included) and, optionally, the cut strip.
 * Walls sit outside the walkable outline. */
export function outerWallGeometry(edges: OuterEdges, style: WallStyle): { body: THREE.BufferGeometry; cap: THREE.BufferGeometry | null } {
  const { height: h, thickness: t } = style;
  const head = style.doorHead ?? DOOR_HEAD_M;
  const body = new MeshBuilder();
  const cap = style.cap ? new MeshBuilder() : null;
  const off = (r: Run): [Pt, Pt] => {
    const dx = r.edge.nx * t / 2, dy = r.edge.ny * t / 2;
    return [[r.a[0] + dx, r.a[1] + dy], [r.b[0] + dx, r.b[1] + dy]];
  };
  for (const r of edges.walls) {
    const [a, b] = off(r);
    body.beam(a, b, t, 0, h, t / 2);
    cap?.beam(a, b, t + 0.004, h, h + 0.03, t / 2);
  }
  if (h - head > 0.05) {
    for (const r of edges.doors) {
      const [a, b] = off(r);
      body.beam(a, b, t, head, h);
      cap?.beam(a, b, t + 0.004, h, h + 0.03);
    }
  }
  return { body: body.geometry(), cap: cap ? cap.geometry() : null };
}

/** Where guard rails go on a floor: its open edges and the sides of its stair openings (not the
 * side a flight arrives from, nor the end where the next flight starts). Venue metres. */
export function guardRailRuns(venue: Venue, floor: Floor, edges: OuterEdges): [Pt, Pt][] {
  const runs: [Pt, Pt][] = [];
  const ring = ccw(floor.walkable as Pt[]);
  const holes = stairOpenings(venue, floor.floor_id);
  const outsideHoles = (m: Pt, skip?: Pt[]) => !holes.some((h) => h !== skip && insideConvex(m, h));
  for (const r of edges.open) runs.push(...splitSegment(r.a, r.b, holes, (m) => outsideHoles(m)));
  if (!holes.length) return runs;
  const feet = flightFeet(venue, floor.floor_id);
  // flights starting on this floor that sit right over an opening guard it with their own rails
  const above = (venue.stairs ?? []).map((s) => stairPlacement(venue, s)).filter((p) => p.lowerFloor === floor.floor_id)
    .map((p) => flightFootprint(p, 0, p.run * 0.25, p.run * 0.75));
  for (const h of holes) {
    const covered = above.some((f) => f.every((p) => insideConvex(p, h, -0.15)));
    // the opening's sides: 0 and 2 along the climb, 3 the foot end, 1 the head (where people arrive)
    const sides = covered ? [3] : [0, 2, 3];
    for (const i of sides) {
      const a = h[i], b = h[(i + 1) % h.length];
      if (i === 3) {
        const mid: Pt = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
        if (feet.some((f) => Math.hypot(f[0] - mid[0], f[1] - mid[1]) < 1.0)) continue;
      }
      runs.push(...splitSegment(a, b, [ring, ...holes.filter((o) => o !== h)], (m) => pointInRing(m, ring) && outsideHoles(m, h)));
    }
  }
  return runs;
}

/** Guard rails: a frame (posts, top and foot rails) and glass infill, as two geometries. */
export function guardRailGeometry(runs: readonly [Pt, Pt][], height = GUARD_RAIL_M): { frame: THREE.BufferGeometry; glass: THREE.BufferGeometry } {
  const frame = new MeshBuilder();
  const glass = new MeshBuilder();
  for (const [a, b] of runs) {
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (len < 0.05) continue;
    frame.beam(a, b, 0.06, height - 0.05, height);
    frame.beam(a, b, 0.04, 0.06, 0.1);
    glass.beam(a, b, 0.02, 0.1, height - 0.05);
    const n = Math.max(1, Math.ceil(len / 1.5));
    for (let i = 0; i <= n; i++) {
      const k = i / n;
      const p: Pt = [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k];
      const ux = (b[0] - a[0]) / len * 0.025, uy = (b[1] - a[1]) / len * 0.025;
      frame.beam([p[0] - ux, p[1] - uy], [p[0] + ux, p[1] + uy], 0.05, 0, height - 0.05);
    }
  }
  return { frame: frame.geometry(), glass: glass.geometry() };
}

/** Columns under an upper floor's open edges, every ~6 m, down `drop` metres to the floor below
 * (the slab's underside is at -slab). */
export function columnGeometry(open: readonly Run[], drop: number, slab: number): THREE.BufferGeometry {
  const b = new MeshBuilder();
  if (drop - slab < 0.3) return b.geometry();
  for (const r of open) {
    const len = Math.hypot(r.b[0] - r.a[0], r.b[1] - r.a[1]);
    const n = Math.max(1, Math.round(len / 6));
    for (let i = 0; i <= n; i++) {
      const k = i / n;
      const x = r.a[0] + (r.b[0] - r.a[0]) * k, y = r.a[1] + (r.b[1] - r.a[1]) * k;
      // set the column just inside the edge
      const cx = x - r.edge.nx * 0.2, cy = y - r.edge.ny * 0.2;
      b.beam([cx - 0.15, cy], [cx + 0.15, cy], 0.3, -drop, -slab);
    }
  }
  return b.geometry();
}

/** Fence posts along an outdoor site's fence runs, about every 5 m. */
export function fencePostGeometry(runs: readonly Run[], height: number): THREE.BufferGeometry {
  const b = new MeshBuilder();
  for (const r of runs) {
    const len = Math.hypot(r.b[0] - r.a[0], r.b[1] - r.a[1]);
    const n = Math.max(1, Math.floor(len / 5));
    for (let i = 0; i <= n; i++) {
      const k = i / n;
      const x = r.a[0] + (r.b[0] - r.a[0]) * k + r.edge.nx * 0.04, y = r.a[1] + (r.b[1] - r.a[1]) * k + r.edge.ny * 0.04;
      b.beam([x - 0.025, y], [x + 0.025, y], 0.05, 0, height + 0.05);
    }
  }
  return b.geometry();
}
