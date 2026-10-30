/** Fixtures recognised by their label (kitchen, toilets, lift, tables, counters) and the meshes that
 * make them read as what they are: a kitchen with counters, a tiled washroom, a metal lift shaft,
 * tables with chairs. Shared by the live view and the .glb export. Venue metres, Y up. */
import * as THREE from "three";
import type { Obstacle, Pt } from "@/api/types";
import { centroid, edgesOf } from "../geom";
import { MeshBuilder } from "./builder";
import { ccw } from "./poly";

export type Fixture = "kitchen" | "toilets" | "lift" | "table" | "counter";

const labelOf = (o: Obstacle) => (o.label ?? "").trim();

/** What a fixture is, from its label (walls are never fixtures). */
export function fixtureOf(o: Obstacle): Fixture | null {
  if (o.kind === "wall") return null;
  const l = labelOf(o);
  if (!l) return null;
  if (/kitchen|kitchenette/i.test(l)) return "kitchen";
  if (/toilet|restroom|washroom|lavator|\bw\.?c\.?\b/i.test(l)) return "toilets";
  if (/\blifts?\b|\belevators?\b/i.test(l)) return "lift";
  if (/^tables?\b|\bdining tables?\b/i.test(l)) return "table";
  if (/counter|reception|check-?out|service desk|\btill\b/i.test(l)) return "counter";
  return null;
}

/** A footprint kept clear for a stair ("Stair structure"): drawn as a faint void in 3D and left
 * out of the exported model, where the stair itself stands. A wall round a stair ("Stairwell
 * wall") is a real wall, not a void. */
export function isStairVoid(o: Obstacle): boolean {
  if (o.kind === "wall") return false;
  return /stair/i.test(o.label ?? o.id);
}

/** A wall enclosing a stair core: kept at full storey height even where room walls are cut low. */
export function isStairwellWall(o: Obstacle): boolean {
  return o.kind === "wall" && /stair/i.test(o.label ?? "");
}

// --- tables ---------------------------------------------------------------------------------

/** One table: centre, rotation (radians, venue x toward y), footprint and height. */
export interface TablePlace {
  id: string;
  x: number;
  y: number;
  angle: number;
  w: number;
  d: number;
  h: number;
}

/** The nominal height the unit table geometry is built at. */
const TABLE_H = 0.75;

/** Where each table stands: its footprint's own axes (the first edge sets the rotation). */
export function tablePlacements(obstacles: readonly Obstacle[]): TablePlace[] {
  const out: TablePlace[] = [];
  for (const o of obstacles) {
    if (fixtureOf(o) !== "table") continue;
    const poly = o.polygon as Pt[];
    if (poly.length < 3) continue;
    const e = edgesOf(poly)[0];
    if (!e) continue;
    const [cx, cy] = centroid(poly);
    let u0 = Infinity, u1 = -Infinity, v0 = Infinity, v1 = -Infinity;
    for (const [px, py] of poly) {
      const dx = px - cx, dy = py - cy;
      const u = dx * e.ux + dy * e.uy, v = -dx * e.uy + dy * e.ux;
      u0 = Math.min(u0, u); u1 = Math.max(u1, u); v0 = Math.min(v0, v); v1 = Math.max(v1, v);
    }
    out.push({ id: o.id, x: cx + (e.ux * (u0 + u1) - e.uy * (v0 + v1)) / 2, y: cy + (e.uy * (u0 + u1) + e.ux * (v0 + v1)) / 2,
      angle: Math.atan2(e.uy, e.ux), w: Math.max(0.3, u1 - u0), d: Math.max(0.3, v1 - v0), h: o.height_m ?? TABLE_H });
  }
  return out;
}

/** The instance matrix that places the unit table (and its chairs) at `p`. */
export function tableMatrix(p: TablePlace, m = new THREE.Matrix4()): THREE.Matrix4 {
  return m.compose(new THREE.Vector3(p.x, 0, -p.y), new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), p.angle),
    new THREE.Vector3(p.w, p.h / TABLE_H, p.d));
}

/** A unit table (1 x 1 m top, 0.75 m high, centred on the origin) and four chairs round it, in
 * world axes, ready to instance with {@link tableMatrix}. */
export function tableUnitGeometry(): { table: THREE.BufferGeometry; chairs: THREE.BufferGeometry } {
  const t = new MeshBuilder();
  t.prism([[-0.5, -0.5], [0.5, -0.5], [0.5, 0.5], [-0.5, 0.5]], TABLE_H - 0.04, TABLE_H);
  t.prism([[-0.06, -0.06], [0.06, -0.06], [0.06, 0.06], [-0.06, 0.06]], 0.03, TABLE_H - 0.04);
  t.prism([[-0.25, -0.25], [0.25, -0.25], [0.25, 0.25], [-0.25, 0.25]], 0, 0.03);
  const c = new MeshBuilder();
  // a chair on each side, its back to the table's outside
  for (const [ux, uy] of [[1, 0], [-1, 0], [0, 1], [0, -1]] as const) {
    const off = 0.8, half = 0.23;
    const at = (s: number, q: number): Pt => [ux * s - uy * q, uy * s + ux * q];
    const box = (s0: number, s1: number, q0: number, q1: number): Pt[] => [at(s0, q0), at(s1, q0), at(s1, q1), at(s0, q1)];
    c.prism(ccw(box(off - half, off + half, -half, half)), 0.42, 0.47);
    c.prism(ccw(box(off - 0.05, off + 0.05, -0.05, 0.05)), 0, 0.42);
    c.prism(ccw(box(off + half - 0.06, off + half, -half, half)), 0.47, 0.9);
  }
  return { table: t.geometry(), chairs: c.geometry() };
}

/** Bake instances of a (non-indexed) unit geometry into one geometry: the export's "Tables". */
export function bakeInstances(unit: THREE.BufferGeometry, matrices: readonly THREE.Matrix4[]): THREE.BufferGeometry {
  const src = unit.getAttribute("position");
  const out = new Float32Array(src.count * 3 * matrices.length);
  const v = new THREE.Vector3();
  matrices.forEach((m, k) => {
    for (let i = 0; i < src.count; i++) {
      v.fromBufferAttribute(src, i).applyMatrix4(m);
      out.set([v.x, v.y, v.z], (k * src.count + i) * 3);
    }
  });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(out, 3));
  if (out.length) g.computeVertexNormals();
  g.computeBoundingSphere();
  return g;
}

// --- rooms ---------------------------------------------------------------------------------

const ROOM_WALL_T = 0.12;
const COUNTER_D = 0.6;
const COUNTER_H = 0.9;
/** A room's own door (into the kitchen, into the washroom). */
const ROOM_DOOR_M = 0.9;
const DOOR_HEAD = 2.1;
/** A WC cubicle: width along the back wall, depth, partition height. */
const CUBICLE_W = 0.9;
const CUBICLE_D = 1.5;
const CUBICLE_H = 2.0;

type Edge = ReturnType<typeof edgesOf>[number];

/** A small room's meshes: partition walls, their cut tops, and its floor. */
export interface RoomGeometry { walls: THREE.BufferGeometry; cap: THREE.BufferGeometry; floor: THREE.BufferGeometry }

/** The edge of a room facing `toward` (the floor's middle): where its door goes. */
function doorEdge(edges: Edge[], toward: Pt | undefined): Edge | undefined {
  if (!toward) return undefined;
  let best: Edge | undefined, score = -Infinity;
  for (const e of edges) {
    if (e.len < ROOM_DOOR_M + 0.4) continue;
    const mx = (e.a[0] + e.b[0]) / 2, my = (e.a[1] + e.b[1]) / 2;
    const s = e.nx * (toward[0] - mx) + e.ny * (toward[1] - my);
    if (s > score) { score = s; best = e; }
  }
  return best;
}

/** One straight piece of partition from a to b, `t` thick, 0 to `h` high; its top face also goes
 * into `cap` (the dark cut line of a plan drawing). */
function wallPiece(b: MeshBuilder, cap: MeshBuilder | undefined, a: Pt, c: Pt, t: number, h: number): void {
  const len = Math.hypot(c[0] - a[0], c[1] - a[1]);
  if (len < 1e-6) return;
  b.beam(a, c, t, 0, h);
  if (!cap) return;
  const nx = (-(c[1] - a[1]) / len) * (t / 2), ny = ((c[0] - a[0]) / len) * (t / 2);
  cap.flat(ccw([[a[0] - nx, a[1] - ny], [c[0] - nx, c[1] - ny], [c[0] + nx, c[1] + ny], [a[0] + nx, a[1] + ny]]), h + 0.006, true);
}

/** Partition walls just inside a room's footprint, `height` high, with a door (and a head over
 * it) in the edge `door` at its middle. */
function roomWalls(b: MeshBuilder, edges: Edge[], height: number, door: Edge | undefined, cap?: MeshBuilder): { door: [number, number] | null } {
  let gap: [number, number] | null = null;
  const T = ROOM_WALL_T;
  for (const e of edges) {
    const off = (s: number): Pt => [e.a[0] + e.ux * s - e.nx * T / 2, e.a[1] + e.uy * s - e.ny * T / 2];
    if (e === door) {
      const d0 = (e.len - ROOM_DOOR_M) / 2, d1 = d0 + ROOM_DOOR_M;
      gap = [d0, d1];
      wallPiece(b, cap, off(-T / 2), off(d0), T, height);
      wallPiece(b, cap, off(d1), off(e.len + T / 2), T, height);
      if (height > DOOR_HEAD + 0.05) b.beam(off(d0), off(d1), T, DOOR_HEAD, height);
    } else {
      wallPiece(b, cap, off(-T / 2), off(e.len + T / 2), T, height);
    }
  }
  return { door: gap };
}

function floorPlate(b: MeshBuilder, ring: Pt[], y: number): void {
  const tris = THREE.ShapeUtils.triangulateShape(ring.map(([x, y]) => new THREE.Vector2(x, y)), []);
  for (const [i, j, k] of tris) b.flat([ring[i], ring[j], ring[k]], y, true);
}

/** A kitchen: partition walls round its footprint with a door toward `toward` (the floor's
 * middle), counters along the inside of each wall (not across the door), an island when there is
 * room, and a tiled floor. Floor-relative. */
export function kitchenGeometry(poly: readonly Pt[], height: number, toward?: Pt): RoomGeometry & { counters: THREE.BufferGeometry } {
  const ring = ccw(poly as Pt[]);
  const walls = new MeshBuilder(), cap = new MeshBuilder(), counters = new MeshBuilder(), floor = new MeshBuilder();
  const edges = edgesOf(ring);
  const door = doorEdge(edges, toward);
  const { door: gap } = roomWalls(walls, edges, height, door, cap);
  for (const e of edges) {
    if (e.len <= 1.4) continue;
    // edgesOf's normal points out; counters stand just inside the wall
    const off = (s: number, d: number): Pt => [e.a[0] + e.ux * s - e.nx * d, e.a[1] + e.uy * s - e.ny * d];
    const d0 = ROOM_WALL_T, s0 = ROOM_WALL_T + (e === door ? 0 : COUNTER_D), s1 = e.len - ROOM_WALL_T - (e === door ? 0 : COUNTER_D);
    const runs: [number, number][] = e === door && gap ? [[s0, gap[0] - 0.1], [gap[1] + 0.1, s1]] : [[s0, s1]];
    for (const [r0, r1] of runs) {
      if (r1 - r0 < 0.5) continue;
      counters.prism(ccw([off(r0, d0), off(r1, d0), off(r1, d0 + COUNTER_D), off(r0, d0 + COUNTER_D)]), 0, COUNTER_H);
    }
  }
  // an island down the middle when the room is deep enough for aisles either side
  const [cx, cy] = centroid(ring);
  const long = edges.reduce((a, b) => (b.len > a.len ? b : a), edges[0]);
  if (long) {
    const across = Math.min(...edges.filter((e) => Math.abs(e.ux * long.uy - e.uy * long.ux) > 0.7).map((e) => e.len).concat([Infinity]));
    if (across >= 4.4 && long.len >= 4) {
      const half = (long.len - 2.6) / 2, hd = 0.45;
      const at = (s: number, q: number): Pt => [cx + long.ux * s - long.uy * q, cy + long.uy * s + long.ux * q];
      counters.prism(ccw([at(-half, -hd), at(half, -hd), at(half, hd), at(-half, hd)]), 0, COUNTER_H);
    }
  }
  floorPlate(floor, ring, 0.012);
  return { walls: walls.geometry(), cap: cap.geometry(), counters: counters.geometry(), floor: floor.geometry() };
}

/** A washroom: partition walls with a door toward `toward`, a row of WC cubicles along the wall
 * opposite the door (partitions and a pan in each), a basin counter along a side wall, and a tiled
 * floor. Floor-relative. */
export function toiletGeometry(poly: readonly Pt[], height: number, toward?: Pt): RoomGeometry & { fittings: THREE.BufferGeometry } {
  const ring = ccw(poly as Pt[]);
  const walls = new MeshBuilder(), cap = new MeshBuilder(), fit = new MeshBuilder(), floor = new MeshBuilder();
  const edges = edgesOf(ring);
  const door = doorEdge(edges, toward);
  roomWalls(walls, edges, height, door, cap);
  floorPlate(floor, ring, 0.012);
  // the back wall: the one facing away from the door (else the longest)
  const back = door
    ? edges.reduce((a, b) => ((b.nx * door.nx + b.ny * door.ny) < (a.nx * door.nx + a.ny * door.ny) ? b : a), edges[0])
    : edges.reduce((a, b) => (b.len > a.len ? b : a), edges[0]);
  if (!back) return { walls: walls.geometry(), cap: cap.geometry(), fittings: fit.geometry(), floor: floor.geometry() };
  const at = (e: Edge, s: number, d: number): Pt => [e.a[0] + e.ux * s - e.nx * d, e.a[1] + e.uy * s - e.ny * d];
  const usable = back.len - 2 * ROOM_WALL_T;
  const depth = Math.min(CUBICLE_D, Math.max(0, (Math.min(...edges.filter((e) => e !== back && Math.abs(e.ux * back.ux + e.uy * back.uy) < 0.3).map((e) => e.len).concat([Infinity])) - ROOM_WALL_T * 2) * 0.6));
  const n = Math.floor(usable / CUBICLE_W);
  if (n >= 1 && depth >= 1.0) {
    const w = usable / n, d0 = ROOM_WALL_T, d1 = ROOM_WALL_T + depth;
    for (let i = 0; i <= n; i++) {
      const s = ROOM_WALL_T + i * w;
      if (i > 0 && i < n) fit.beam(at(back, s, d0), at(back, s, d1), 0.04, 0.15, CUBICLE_H);
      if (i < n) {
        // the pan against the back wall, and the cubicle's front with a door-width gap
        const m = s + w / 2;
        fit.prism(ccw([at(back, m - 0.19, d0), at(back, m + 0.19, d0), at(back, m + 0.19, d0 + 0.6), at(back, m - 0.19, d0 + 0.6)]), 0, 0.42);
        fit.beam(at(back, s, d1), at(back, s + w * 0.18, d1), 0.04, 0.15, CUBICLE_H);
        fit.beam(at(back, s + w * 0.82, d1), at(back, s + w, d1), 0.04, 0.15, CUBICLE_H);
      }
    }
  }
  // basins along a side wall, clear of the cubicles
  const side = edges.find((e) => e !== back && e !== door && Math.abs(e.ux * back.ux + e.uy * back.uy) < 0.3);
  if (side) {
    // from the side wall's end away from the back wall
    const nearBack = Math.hypot(side.a[0] - back.b[0], side.a[1] - back.b[1]) < 0.05 || Math.hypot(side.a[0] - back.a[0], side.a[1] - back.a[1]) < 0.05;
    const r0 = nearBack ? ROOM_WALL_T + depth + 0.3 : ROOM_WALL_T + 0.2;
    const r1 = nearBack ? side.len - ROOM_WALL_T - 0.2 : side.len - ROOM_WALL_T - depth - 0.3;
    if (r1 - r0 >= 0.6) fit.prism(ccw([at(side, r0, ROOM_WALL_T), at(side, r1, ROOM_WALL_T), at(side, r1, ROOM_WALL_T + 0.5), at(side, r0, ROOM_WALL_T + 0.5)]), 0.78, 0.86);
  }
  return { walls: walls.geometry(), cap: cap.geometry(), fittings: fit.geometry(), floor: floor.geometry() };
}

/** A lift: the shaft (its footprint extruded to `height`) and a pair of doors on the side that
 * faces `toward` (the floor's centre). Floor-relative. */
export function liftGeometry(poly: readonly Pt[], height: number, toward: Pt): { shaft: THREE.BufferGeometry; doors: THREE.BufferGeometry } {
  const ring = ccw(poly as Pt[]);
  const shaft = new MeshBuilder(), doors = new MeshBuilder();
  const tris = THREE.ShapeUtils.triangulateShape(ring.map(([x, y]) => new THREE.Vector2(x, y)), []);
  for (const [i, j, k] of tris) shaft.flat([ring[i], ring[j], ring[k]], height, true);
  const edges = edgesOf(ring);
  for (const e of edges) shaft.side(e.a, e.b, 0, height, [e.nx, e.ny]);
  let best = edges[0], score = -Infinity;
  for (const e of edges) {
    const mx = (e.a[0] + e.b[0]) / 2, my = (e.a[1] + e.b[1]) / 2;
    const s = (e.nx * (toward[0] - mx) + e.ny * (toward[1] - my)) * Math.min(1, e.len);
    if (s > score) { score = s; best = e; }
  }
  if (best && best.len > 0.9) {
    const dw = Math.min(1.0, best.len - 0.4) / 2, mid = best.len / 2;
    const at = (s: number): Pt => [best.a[0] + best.ux * s + best.nx * 0.02, best.a[1] + best.uy * s + best.ny * 0.02];
    // two leaves with a hairline between them, and a head over them
    doors.beam(at(mid - dw), at(mid - 0.01), 0.04, 0.02, 2.1);
    doors.beam(at(mid + 0.01), at(mid + dw), 0.04, 0.02, 2.1);
    doors.beam(at(mid - dw - 0.08), at(mid + dw + 0.08), 0.05, 2.1, 2.25);
  }
  return { shaft: shaft.geometry(), doors: doors.geometry() };
}

let tileTexture: THREE.DataTexture | null = null;

/** A small tile pattern (light grout lines) for washroom walls; world-metre UVs repeat it about
 * every 0.3 m. Shared, made once. */
export function tileMap(): THREE.DataTexture {
  if (tileTexture) return tileTexture;
  const n = 16;
  const data = new Uint8Array(n * n * 4);
  for (let y = 0; y < n; y++) {
    for (let x = 0; x < n; x++) {
      const grout = x === 0 || y === 0;
      const v = grout ? 255 : 228 + ((x * 7 + y * 13) % 5);
      data.set([v, v, v, 255], (y * n + x) * 4);
    }
  }
  const t = new THREE.DataTexture(data, n, n);
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  t.repeat.set(1 / 0.3, 1 / 0.3);
  t.magFilter = THREE.LinearFilter;
  t.minFilter = THREE.LinearMipmapLinearFilter;
  t.generateMipmaps = true;
  t.colorSpace = THREE.SRGBColorSpace;
  t.needsUpdate = true;
  tileTexture = t;
  return t;
}
