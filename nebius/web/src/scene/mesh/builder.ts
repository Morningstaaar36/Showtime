/** A tiny triangle soup builder: flat-shaded, non-indexed, world-space positions (three.js Y up).
 * Venue (x, y) maps to world (x, -y); `v(x, y, h)` does that. */
import * as THREE from "three";
import type { Pt } from "@/api/types";

export type V3 = [number, number, number];

/** World point from venue x, y and height. */
export const v = (x: number, y: number, h: number): V3 => [x, h, -y];

export class MeshBuilder {
  private pos: number[] = [];

  get triangles(): number {
    return this.pos.length / 9;
  }

  /** One triangle, wound so its face normal points along `toward` (when given). */
  tri(a: V3, b: V3, c: V3, toward?: V3): this {
    const ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    const wx = c[0] - a[0], wy = c[1] - a[1], wz = c[2] - a[2];
    const nx = uy * wz - uz * wy, ny = uz * wx - ux * wz, nz = ux * wy - uy * wx;
    // slivers from clipping have no normal: drop them
    if (nx * nx + ny * ny + nz * nz < 1e-14) return this;
    if (toward && nx * toward[0] + ny * toward[1] + nz * toward[2] < 0) [b, c] = [c, b];
    this.pos.push(...a, ...b, ...c);
    return this;
  }

  quad(a: V3, b: V3, c: V3, d: V3, toward?: V3): this {
    return this.tri(a, b, c, toward).tri(a, c, d, toward);
  }

  /** A convex polygon (venue coords) at height h, facing up or down. */
  flat(poly: readonly Pt[], h: number, up: boolean): this {
    const n: V3 = [0, up ? 1 : -1, 0];
    for (let i = 1; i + 1 < poly.length; i++) {
      this.tri(v(poly[0][0], poly[0][1], h), v(poly[i][0], poly[i][1], h), v(poly[i + 1][0], poly[i + 1][1], h), n);
    }
    return this;
  }

  /** A vertical face over the venue segment a-b from height h0 to h1, facing `normal` (venue xy). */
  side(a: Pt, b: Pt, h0: number, h1: number, normal: Pt): this {
    return this.quad(v(a[0], a[1], h0), v(b[0], b[1], h0), v(b[0], b[1], h1), v(a[0], a[1], h1), [normal[0], 0, -normal[1]]);
  }

  /** A box along the venue segment a-b: `width` across it, from height h0 to h1. Open ends are
   * capped. `grow` extends it past both ends (closes wall corners). */
  beam(a: Pt, b: Pt, width: number, h0: number, h1: number, grow = 0): this {
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    if (len < 1e-6 || h1 - h0 < 1e-6) return this;
    const ux = (b[0] - a[0]) / len, uy = (b[1] - a[1]) / len;
    const nx = -uy * (width / 2), ny = ux * (width / 2);
    const a0: Pt = [a[0] - ux * grow, a[1] - uy * grow], b0: Pt = [b[0] + ux * grow, b[1] + uy * grow];
    const ring: Pt[] = [[a0[0] - nx, a0[1] - ny], [b0[0] - nx, b0[1] - ny], [b0[0] + nx, b0[1] + ny], [a0[0] + nx, a0[1] + ny]];
    return this.prism(ring, h0, h1);
  }

  /** A convex ring (venue coords) extruded from h0 to h1, closed. */
  prism(ring: readonly Pt[], h0: number, h1: number): this {
    this.flat(ring, h1, true).flat(ring, h0, false);
    const cx = ring.reduce((s, p) => s + p[0], 0) / ring.length, cy = ring.reduce((s, p) => s + p[1], 0) / ring.length;
    for (let i = 0; i < ring.length; i++) {
      const p = ring[i], q = ring[(i + 1) % ring.length];
      const mx = (p[0] + q[0]) / 2 - cx, my = (p[1] + q[1]) / 2 - cy;
      this.side(p, q, h0, h1, [mx, my]);
    }
    return this;
  }

  /** A box between two world points (any direction): `size` across (horizontal side) and
   * `depth` the other way (square when omitted). */
  bar(p: V3, q: V3, size: number, depth = size): this {
    const d = new THREE.Vector3(q[0] - p[0], q[1] - p[1], q[2] - p[2]);
    const len = d.length();
    if (len < 1e-6) return this;
    d.normalize();
    const ref = Math.abs(d.y) < 0.9 ? new THREE.Vector3(0, 1, 0) : new THREE.Vector3(1, 0, 0);
    const s1 = new THREE.Vector3().crossVectors(d, ref).normalize().multiplyScalar(size / 2);
    const s2 = new THREE.Vector3().crossVectors(d, s1).normalize().multiplyScalar(depth / 2);
    const P = new THREE.Vector3(...p), Q = new THREE.Vector3(...q);
    const corner = (o: THREE.Vector3, i: number): V3 => {
      const a = i & 1 ? 1 : -1, b = i & 2 ? 1 : -1;
      const c = o.clone().addScaledVector(s1, a).addScaledVector(s2, b);
      return [c.x, c.y, c.z];
    };
    const ring = [0, 1, 3, 2];
    const mid = P.clone().add(Q).multiplyScalar(0.5);
    for (let k = 0; k < 4; k++) {
      const i = ring[k], j = ring[(k + 1) % 4];
      const a = corner(P, i), b = corner(P, j), c = corner(Q, j), e = corner(Q, i);
      const out = new THREE.Vector3((a[0] + c[0]) / 2, (a[1] + c[1]) / 2, (a[2] + c[2]) / 2).sub(mid);
      this.quad(a, b, c, e, [out.x, out.y, out.z]);
    }
    const capP = ring.map((i) => corner(P, i)), capQ = ring.map((i) => corner(Q, i));
    const back: V3 = [-d.x, -d.y, -d.z], fwd: V3 = [d.x, d.y, d.z];
    this.quad(capP[0], capP[1], capP[2], capP[3], back);
    this.quad(capQ[0], capQ[1], capQ[2], capQ[3], fwd);
    return this;
  }

  /** Append another builder's triangles. */
  add(other: MeshBuilder): this {
    this.pos.push(...other.pos);
    return this;
  }

  /** The finished geometry (flat normals); empty builders give an empty geometry. */
  geometry(): THREE.BufferGeometry {
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(this.pos, 3));
    if (this.pos.length) g.computeVertexNormals();
    g.computeBoundingSphere();
    return g;
  }
}

/** Triangle count of a geometry (indexed or not). */
export function triangleCount(g: THREE.BufferGeometry): number {
  return (g.index ? g.index.count : g.getAttribute("position")?.count ?? 0) / 3;
}

/** Drop zero-area triangles (a triangulator's slivers between collinear points) from a
 * non-indexed geometry, so every normal is a unit vector. Returns the same geometry. */
export function dropSlivers(g: THREE.BufferGeometry): THREE.BufferGeometry {
  if (g.index) return g;
  const p = g.getAttribute("position");
  const keep: number[] = [];
  const a = new THREE.Vector3(), b = new THREE.Vector3(), c = new THREE.Vector3();
  for (let i = 0; i < p.count; i += 3) {
    a.fromBufferAttribute(p, i); b.fromBufferAttribute(p, i + 1); c.fromBufferAttribute(p, i + 2);
    if (b.sub(a).cross(c.sub(a)).lengthSq() >= 1e-14) keep.push(i);
  }
  if (keep.length * 3 === p.count) return g;
  for (const name of Object.keys(g.attributes)) {
    const attr = g.getAttribute(name);
    const out = new Float32Array(keep.length * 3 * attr.itemSize);
    keep.forEach((i, k) => {
      for (let j = 0; j < 3 * attr.itemSize; j++) out[k * 3 * attr.itemSize + j] = attr.array[i * attr.itemSize + j];
    });
    g.setAttribute(name, new THREE.BufferAttribute(out, attr.itemSize));
  }
  g.clearGroups();
  return g;
}
