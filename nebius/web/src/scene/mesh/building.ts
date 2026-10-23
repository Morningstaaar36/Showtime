/** The venue as a clean 3D model for export: one group per floor (named by the floor), one mesh
 * per object (named by its label), stairs with rails. Metres, Y up. No people, labels or UI. */
import * as THREE from "three";
import type { Floor, Obstacle, Pt, StageParams, Venue } from "@/api/types";
import { floorLabels } from "@/lib/venueOps";
import { exitName } from "@/lib/venueText";
import { bbox, doorwayOf, FENCE_M, shapeOf, wallThickness, WALL_INDOOR_M, WALL_T } from "../geom";
import type { ScenePalette } from "../palette";
import { dropSlivers, MeshBuilder } from "./builder";
import { columnGeometry, DOOR_HEAD_M, floorBelow, guardRailGeometry, guardRailRuns, outerEdges, outerWallGeometry } from "./floor";
import { slabGeometry } from "./slab";
import { stairGeometry, stairOpenings, stairPlacement } from "./stairs";

/** Default heights of obstacles by kind (metres), when an obstacle has none of its own. */
export const OBSTACLE_HEIGHT: Record<string, number> = {
  wall: WALL_INDOOR_M, booth: 2.6, bar: 2.4, seating: 0.55, column: 3.0, barrier: 1.1,
  fence: 1.2, other: 1.4, stage: 1.0,
};

export const SLAB_M = 0.3;
/** Storey height of the top floor (nothing above it to measure to). */
const TOP_STOREY_M = 3.2;

/** Floor-to-floor height: to the next floor up, or a default for the top floor. */
export function storeyHeight(venue: Venue, floor: Floor): number {
  const e = floor.elevation_m ?? 0;
  const above = venue.floors.map((f) => f.elevation_m ?? 0).filter((x) => x > e + 0.01);
  return above.length ? Math.min(...above) - e : TOP_STOREY_M;
}

/** "1st floor", the floor's own name first. */
export function floorName(venue: Venue, floor: Floor): string {
  if (floor.name?.trim()) return floor.name.trim();
  const l = floorLabels(venue).get(floor.floor_id) ?? floor.floor_id;
  return l === "Ground" ? "Ground floor" : l.startsWith("B") ? `Basement ${l.slice(1)}` : `${l} floor`;
}

/** An obstacle's body: its footprint extruded, or a wall drawn along its centreline as one box per
 * segment at the wall's thickness. Floor-relative, world axes. */
export function obstacleGeometry(o: Obstacle, height: number): THREE.BufferGeometry {
  if (o.kind === "wall" && o.line && o.line.length >= 2) {
    const line = o.line as Pt[];
    const t = wallThickness(o.polygon as Pt[], line);
    const b = new MeshBuilder();
    for (let i = 1; i < line.length; i++) b.beam(line[i - 1], line[i], t, 0, height, t / 2);
    return b.geometry();
  }
  const g = new THREE.ExtrudeGeometry(shapeOf(o.polygon as Pt[]), { depth: height, bevelEnabled: false });
  g.rotateX(-Math.PI / 2);
  g.deleteAttribute("uv");
  return dropSlivers(g);
}

/** An exit's gate frame (two posts and a head), floor-relative; null if it is not on the outline. */
export function exitFrameGeometry(floor: Floor, exit: Floor["exits"][number], head: number, post = 0.12): THREE.BufferGeometry | null {
  const d = doorwayOf(floor.walkable as Pt[], exit);
  if (!d) return null;
  const b = new MeshBuilder();
  const { ux, uy } = d.edge;
  const at = (s: number): Pt => [d.cx + ux * s, d.cy + uy * s];
  const half = d.width / 2;
  for (const s of [-half, half]) b.beam(at(s - post / 2), at(s + post / 2), post, 0, head - post);
  b.beam(at(-half - post / 2), at(half + post / 2), post, head - post, head);
  return b.geometry();
}

function stageGeometry(o: Obstacle, stage: StageParams | null): { deck: THREE.BufferGeometry; frame: THREE.BufferGeometry | null } {
  const deckH = stage ? 1.5 : o.height_m ?? 1.0;
  const deck = obstacleGeometry({ ...o, kind: "other", line: null }, deckH);
  const roofH = stage?.roof_height_m ?? 0;
  if (!stage || roofH <= deckH) return { deck, frame: null };
  const [x0, y0, x1, y1] = bbox(o.polygon as Pt[]);
  const b = new MeshBuilder();
  const legs = Math.max(2, Math.floor(stage.legs / 2));
  for (const y of [y0, y1]) {
    for (let i = 0; i < legs; i++) {
      const x = x0 + ((x1 - x0) * i) / (legs - 1);
      b.beam([x - 0.12, y], [x + 0.12, y], 0.24, 0, roofH);
    }
    b.beam([x0 - 0.2, y], [x1 + 0.2, y], 0.3, roofH - 0.21, roofH + 0.21);
  }
  b.beam([x0 - 0.6, (y0 + y1) / 2], [x1 + 0.6, (y0 + y1) / 2], y1 - y0 + 1.2, roofH + 0.42, roofH + 0.48);
  return { deck, frame: b.geometry() };
}

type Materials = Record<"floor" | "wall" | "rail" | "glass" | "stair" | "exit" | "blocked" | "obstacle" | "booth" | "barrier" | "stage" | "frame" | "water", THREE.Material>;

function materials(p: ScenePalette): Materials {
  const m = (name: string, color: string, extra: THREE.MeshStandardMaterialParameters = {}) =>
    Object.assign(new THREE.MeshStandardMaterial({ color, roughness: 0.85, metalness: 0, ...extra }), { name });
  return {
    floor: m("Floor", p.floor), wall: m("Wall", p.wall), rail: m("Rail", p.edge, { roughness: 0.5, metalness: 0.4 }),
    glass: m("Glass", "#cfe3f2", { transparent: true, opacity: 0.35, roughness: 0.1 }),
    stair: m("Stair", p.stair), exit: m("Exit", p.egress, { emissive: new THREE.Color(p.egress), emissiveIntensity: 0.3 }),
    blocked: m("Blocked exit", p.danger), obstacle: m("Fixture", p.obstacle), booth: m("Booth", p.booth),
    barrier: m("Barrier", p.barrier, { roughness: 0.5, metalness: 0.35 }), stage: m("Stage deck", p.stageDeck),
    frame: m("Stage frame", p.stageFrame, { roughness: 0.5, metalness: 0.5 }), water: m("Water", "#7fb2e0", { transparent: true, opacity: 0.85 }),
  };
}

function mesh(name: string, g: THREE.BufferGeometry, mat: THREE.Material): THREE.Mesh | null {
  if (!g.getAttribute("position")?.count) { g.dispose(); return null; }
  const m = new THREE.Mesh(g, mat);
  m.name = name;
  return m;
}

/** The whole venue as a THREE.Group (not exploded): floors at their elevations, stairs between. */
export function buildVenueModel(venue: Venue, palette: ScenePalette): THREE.Group {
  const mats = materials(palette);
  const outdoor = venue.mode === "outdoor";
  const root = new THREE.Group();
  root.name = venue.name || "Venue";
  const lowest = Math.min(...venue.floors.map((f) => f.elevation_m ?? 0));
  for (const floor of venue.floors) {
    const g = new THREE.Group();
    g.name = floorName(venue, floor);
    g.position.y = floor.elevation_m ?? 0;
    const add = (m: THREE.Mesh | null) => { if (m) g.add(m); };
    const isLowest = (floor.elevation_m ?? 0) <= lowest + 0.01;
    const storey = storeyHeight(venue, floor);
    const hasAbove = venue.floors.some((f) => (f.elevation_m ?? 0) > (floor.elevation_m ?? 0) + 0.01);
    const wallH = outdoor ? FENCE_M : Math.max(DOOR_HEAD_M + 0.3, storey - (hasAbove ? SLAB_M : 0));
    const slab = slabGeometry(floor.walkable as Pt[], stairOpenings(venue, floor.floor_id), isLowest ? 0.2 : SLAB_M);
    add(mesh("Floor slab", slab.geometry, mats.floor));
    const below = floorBelow(venue, floor);
    const edges = outerEdges(floor, below);
    const walls = outerWallGeometry(edges, { height: wallH, thickness: outdoor ? 0.08 : WALL_T });
    add(mesh(outdoor ? "Fence" : "Outer walls", walls.body, outdoor ? mats.barrier : mats.wall));
    const rails = guardRailGeometry(guardRailRuns(venue, floor, edges));
    add(mesh("Guard rail", rails.frame, mats.rail));
    add(mesh("Guard rail glass", rails.glass, mats.glass));
    if (below) add(mesh("Columns", columnGeometry(edges.open, (floor.elevation_m ?? 0) - (below.elevation_m ?? 0), SLAB_M), mats.wall));
    for (const o of floor.obstacles) {
      const name = o.label ?? o.id;
      if (o.kind === "stage") {
        const s = stageGeometry(o, venue.stage ?? null);
        add(mesh(name, s.deck, mats.stage));
        if (s.frame) add(mesh(`${name} roof`, s.frame, mats.frame));
        continue;
      }
      const h = o.kind === "wall" && !outdoor && !o.height_m ? wallH : o.height_m ?? OBSTACLE_HEIGHT[o.kind ?? "other"] ?? 1.4;
      const mat = o.id.startsWith("water_") ? mats.water : o.kind === "wall" ? mats.wall
        : o.kind === "barrier" || o.kind === "fence" ? mats.barrier : o.kind === "booth" || o.kind === "bar" ? mats.booth : mats.obstacle;
      add(mesh(name, obstacleGeometry(o, h), mat));
    }
    for (const e of floor.exits) {
      const fg = exitFrameGeometry(floor, e, outdoor ? 2.8 : DOOR_HEAD_M);
      if (fg) add(mesh(`Exit · ${exitName(floor, e)}`, fg, e.blocked ? mats.blocked : mats.exit));
    }
    root.add(g);
  }
  const stairs = new THREE.Group();
  stairs.name = "Stairs";
  const name = (id: string) => floorName(venue, venue.floors.find((f) => f.floor_id === id) ?? venue.floors[0]);
  (venue.stairs ?? []).forEach((s, i) => {
    const p = stairPlacement(venue, s);
    const geo = stairGeometry(p.run, p.rise, p.width);
    const sg = new THREE.Group();
    sg.name = `Stair ${i + 1} · ${name(p.upperFloor)} to ${name(p.lowerFloor)}`;
    sg.position.set(p.foot[0], p.yBot, -p.foot[1]);
    sg.rotation.y = p.angle;
    const body = mesh("Steps", geo.body, mats.stair);
    const rails = mesh("Handrails", geo.rails, mats.rail);
    if (body) sg.add(body);
    if (rails) sg.add(rails);
    stairs.add(sg);
  });
  if (stairs.children.length) root.add(stairs);
  return root;
}

/** Free a model built by {@link buildVenueModel}. */
export function disposeModel(root: THREE.Object3D): void {
  const mats = new Set<THREE.Material>();
  root.traverse((o) => {
    if (o instanceof THREE.Mesh) {
      o.geometry.dispose();
      (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => mats.add(m));
    }
  });
  mats.forEach((m) => m.dispose());
}

/** Total triangles in a model. */
export function modelTriangles(root: THREE.Object3D): number {
  let n = 0;
  root.traverse((o) => {
    if (o instanceof THREE.Mesh) {
      const g = o.geometry as THREE.BufferGeometry;
      n += (g.index ? g.index.count : g.getAttribute("position").count) / 3;
    }
  });
  return n;
}
