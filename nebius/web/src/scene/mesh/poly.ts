/** 2D polygon helpers for mesh generation (venue metres, x east, y north). Pure functions. */
import type { Pt } from "@/api/types";

const EPS = 1e-7;

export function signedArea(poly: readonly Pt[]): number {
  let a = 0;
  for (let i = 0; i < poly.length; i++) {
    const p = poly[i], q = poly[(i + 1) % poly.length];
    a += p[0] * q[1] - q[0] * p[1];
  }
  return a / 2;
}

/** The ring counter-clockwise, without a repeated closing point or zero-length edges. */
export function ccw(poly: readonly Pt[]): Pt[] {
  const out: Pt[] = [];
  for (const p of poly) {
    const last = out[out.length - 1];
    if (!last || Math.hypot(p[0] - last[0], p[1] - last[1]) > 1e-6) out.push([p[0], p[1]]);
  }
  if (out.length > 1 && Math.hypot(out[0][0] - out[out.length - 1][0], out[0][1] - out[out.length - 1][1]) <= 1e-6) out.pop();
  return signedArea(out) < 0 ? out.reverse() : out;
}

const cross = (a: Pt, b: Pt, p: Pt) => (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]);

/** Sutherland-Hodgman: the part of a convex polygon on the left of a->b (keepLeft) or the right. */
export function clipHalfPlane(poly: readonly Pt[], a: Pt, b: Pt, keepLeft: boolean): Pt[] {
  const out: Pt[] = [];
  const side = (p: Pt) => (keepLeft ? cross(a, b, p) : -cross(a, b, p));
  for (let i = 0; i < poly.length; i++) {
    const p = poly[i], q = poly[(i + 1) % poly.length];
    const sp = side(p), sq = side(q);
    if (sp >= -EPS) out.push(p);
    if ((sp > EPS && sq < -EPS) || (sp < -EPS && sq > EPS)) {
      const t = sp / (sp - sq);
      out.push([p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t]);
    }
  }
  return out;
}

/** A convex polygon minus a convex polygon (CCW), as convex pieces. */
export function subtractConvex(poly: readonly Pt[], hole: readonly Pt[]): Pt[][] {
  const pieces: Pt[][] = [];
  let rest: Pt[] = [...poly];
  for (let i = 0; i < hole.length && rest.length >= 3; i++) {
    const a = hole[i], b = hole[(i + 1) % hole.length];
    const outside = clipHalfPlane(rest, a, b, false);
    if (outside.length >= 3 && Math.abs(signedArea(outside)) > 1e-6) pieces.push(outside);
    rest = clipHalfPlane(rest, a, b, true);
  }
  // nothing of the hole touched the polygon: keep it whole
  if (pieces.length === 0 && (rest.length < 3 || Math.abs(signedArea(rest)) < 1e-6)) return [[...poly]];
  return pieces;
}

export function pointInRing(p: Pt, ring: readonly Pt[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if (yi > p[1] !== yj > p[1] && p[0] < ((xj - xi) * (p[1] - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

/** Point strictly inside a convex CCW polygon (a margin keeps edge points out). */
export function insideConvex(p: Pt, poly: readonly Pt[], margin = 1e-6): boolean {
  for (let i = 0; i < poly.length; i++) {
    const a = poly[i], b = poly[(i + 1) % poly.length];
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]) || 1;
    if (cross(a, b, p) / len <= margin) return false;
  }
  return true;
}

/** Parameters (0..1) where segment a->b crosses the ring's edges, sorted, with 0 and 1. */
function cuts(a: Pt, b: Pt, rings: readonly (readonly Pt[])[]): number[] {
  const ts = [0, 1];
  const dx = b[0] - a[0], dy = b[1] - a[1];
  for (const ring of rings) {
    for (let i = 0; i < ring.length; i++) {
      const p = ring[i], q = ring[(i + 1) % ring.length];
      const ex = q[0] - p[0], ey = q[1] - p[1];
      const den = dx * ey - dy * ex;
      if (Math.abs(den) < 1e-12) continue;
      const t = ((p[0] - a[0]) * ey - (p[1] - a[1]) * ex) / den;
      const u = ((p[0] - a[0]) * dy - (p[1] - a[1]) * dx) / den;
      if (t > 1e-9 && t < 1 - 1e-9 && u >= -1e-9 && u <= 1 + 1e-9) ts.push(t);
    }
  }
  return ts.sort((x, y) => x - y);
}

/** The pieces of segment a->b for which `keep(midpoint)` holds, split where it crosses `rings`. */
export function splitSegment(a: Pt, b: Pt, rings: readonly (readonly Pt[])[], keep: (p: Pt) => boolean, minLen = 0.02): [Pt, Pt][] {
  const ts = cuts(a, b, rings);
  const at = (t: number): Pt => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  const out: [Pt, Pt][] = [];
  const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
  for (let i = 1; i < ts.length; i++) {
    const t0 = ts[i - 1], t1 = ts[i];
    if ((t1 - t0) * len < minLen) continue;
    if (!keep(at((t0 + t1) / 2))) continue;
    const last = out[out.length - 1];
    // join with the previous kept piece when they touch
    if (last && Math.hypot(last[1][0] - at(t0)[0], last[1][1] - at(t0)[1]) < 1e-6) last[1] = at(t1);
    else out.push([at(t0), at(t1)]);
  }
  return out;
}

/** Distance from p to segment a-b. */
export function segDist(p: Pt, a: Pt, b: Pt): number {
  const dx = b[0] - a[0], dy = b[1] - a[1];
  const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
  return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
}
