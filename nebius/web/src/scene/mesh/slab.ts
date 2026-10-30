/** Floor slabs with real thickness and openings cut where stairs pass through. */
import * as THREE from "three";
import type { Pt } from "@/api/types";
import { MeshBuilder } from "./builder";
import { ccw, insideConvex, pointInRing, splitSegment, subtractConvex } from "./poly";

export interface Slab {
  /** top face at y = 0, bottom at y = -thickness, side faces round the outline and the openings */
  geometry: THREE.BufferGeometry;
  /** the same plate split in two: top and bottom faces, and the side faces (the slab's edge band,
   * drawn darker so each storey reads as a line). Built only when asked for. */
  parts?: { faces: THREE.BufferGeometry; rim: THREE.BufferGeometry };
  /** the slab's top edges (outline and opening rims), venue metres: for thin ink lines */
  edges: [Pt, Pt][];
  /** the openings that actually cut this slab (counter-clockwise) */
  openings: Pt[][];
}

/** A floor plate over `walkable`, `thickness` deep (0 = the top face alone), with each convex
 * opening cut out. Openings may cross the outline (a stair under a mezzanine's edge). */
export function slabGeometry(walkable: readonly Pt[], openings: readonly (readonly Pt[])[], thickness: number, split = false): Slab {
  const ring = ccw(walkable as Pt[]);
  const b = new MeshBuilder();
  const r = new MeshBuilder();
  const edges: [Pt, Pt][] = [];
  if (ring.length < 3) return { geometry: b.geometry(), edges, openings: [] };
  const [x0, y0, x1, y1] = bounds(ring);
  const holes = openings.map((h) => ccw(h as Pt[])).filter((h) => {
    if (h.length < 3) return false;
    const [hx0, hy0, hx1, hy1] = bounds(h);
    if (hx1 < x0 || hx0 > x1 || hy1 < y0 || hy0 > y1) return false;
    // keep it only when part of it lies on the plate
    return h.some((p) => pointInRing(p, ring)) || ring.some((p) => insideConvex(p, h)) || crosses(ring, h);
  });
  const tris = THREE.ShapeUtils.triangulateShape(ring.map(([x, y]) => new THREE.Vector2(x, y)), []);
  for (const [i, j, k] of tris) {
    let pieces: Pt[][] = [[ring[i], ring[j], ring[k]]];
    for (const h of holes) pieces = pieces.flatMap((p) => subtractConvex(p, h));
    for (const p of pieces) {
      b.flat(p, 0, true);
      if (thickness > 0) b.flat(p, -thickness, false);
    }
  }
  const inHole = (m: Pt, skip?: Pt[]) => holes.some((h) => h !== skip && insideConvex(m, h));
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i], c = ring[(i + 1) % ring.length];
    const len = Math.hypot(c[0] - a[0], c[1] - a[1]);
    const out: Pt = [(c[1] - a[1]) / len, -(c[0] - a[0]) / len];
    for (const [p, q] of splitSegment(a, c, holes, (m) => !inHole(m))) {
      edges.push([p, q]);
      if (thickness > 0) r.side(p, q, -thickness, 0, out);
    }
  }
  for (const h of holes) {
    const others = holes.filter((o) => o !== h);
    for (let i = 0; i < h.length; i++) {
      const a = h[i], c = h[(i + 1) % h.length];
      const len = Math.hypot(c[0] - a[0], c[1] - a[1]);
      const into: Pt = [-(c[1] - a[1]) / len, (c[0] - a[0]) / len];
      for (const [p, q] of splitSegment(a, c, [ring, ...others], (m) => pointInRing(m, ring) && !inHole(m, h))) {
        edges.push([p, q]);
        if (thickness > 0) r.side(p, q, -thickness, 0, into);
      }
    }
  }
  const parts = split ? { faces: b.geometry(), rim: r.geometry() } : undefined;
  return { geometry: b.add(r).geometry(), edges, openings: holes, parts };
}

function bounds(poly: readonly Pt[]): [number, number, number, number] {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const [x, y] of poly) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
  return [x0, y0, x1, y1];
}

function crosses(ring: readonly Pt[], h: readonly Pt[]): boolean {
  for (let i = 0; i < h.length; i++) {
    if (splitSegment(h[i], h[(i + 1) % h.length], [ring], (m) => pointInRing(m, ring as Pt[])).length) return true;
  }
  return false;
}
