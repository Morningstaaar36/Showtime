import type * as THREE from "three";
import { describe, expect, it } from "vitest";
import type { Floor, Pt, Stair, Venue } from "@/api/types";
import { triangleCount } from "./builder";
import { buildVenueModel, disposeModel, modelTriangles } from "./building";
import { floorBelow, guardRailRuns, outerEdges, outerWallGeometry } from "./floor";
import { subtractConvex } from "./poly";
import { slabGeometry } from "./slab";
import { stairGeometry, stairOpenings } from "./stairs";
import { LIGHT_PALETTE } from "../palette";

const rect = (x0: number, y0: number, x1: number, y1: number): Pt[] => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];

function floor(id: string, elev: number, walkable: Pt[], extra: Partial<Floor> = {}): Floor {
  return { floor_id: id, name: id === "F0" ? "Ground" : `Level ${id.slice(1)}`, elevation_m: elev, walkable, obstacles: [], exits: [], zones: [], ...extra } as Floor;
}

/** A tower like the generated hospital: stacked straight flights at both ends, one front door. */
function tower(storeys: number): Venue {
  const floors: Floor[] = [];
  const stairs: Stair[] = [];
  for (let i = 0; i < storeys; i++) {
    const walls = Array.from({ length: 12 }, (_, k) => ({
      id: `w${i}_${k}`, kind: "wall", label: null, height_m: null, line: null,
      polygon: rect(5 * k + 2, 10, 5 * k + 2.15, 20),
    }));
    floors.push(floor(`F${i}`, i * 3.5, rect(0, 0, 60, 25), {
      obstacles: walls as Floor["obstacles"],
      exits: i === 0 ? [{ id: "front", polygon: rect(28.8, 0.02, 31.2, 0.42), width_m: 2.4, blocked: false, label: "Main entrance" }] : [],
    }));
    if (i > 0) {
      for (const [name, top, bottom] of [["a", rect(1.2, 11.7, 3.7, 13.3), rect(4.2, 11.7, 6.7, 13.3)], ["b", rect(56.3, 11.7, 58.8, 13.3), rect(53.3, 11.7, 55.8, 13.3)]] as const) {
        stairs.push({ id: `stair_${name}_${i}`, from_floor: `F${i}`, to_floor: `F${i - 1}`, top_polygon: top, bottom_polygon: bottom, width_m: 1.2, length_m: 6.95 } as Stair);
      }
    }
  }
  return { venue_id: "t", name: "Tower", description: "", mode: "indoor", floors, stairs, routes: [], stage: null } as unknown as Venue;
}

/** A hall with a mezzanine along its north side and one stair up to it. */
function hall(): Venue {
  return {
    venue_id: "h", name: "Hall", description: "", mode: "indoor", routes: [], stage: null,
    floors: [floor("F0", 0, rect(0, 0, 40, 25)), floor("F1", 4.5, rect(0, 15, 40, 25))],
    stairs: [{ id: "s", from_floor: "F1", to_floor: "F0", top_polygon: rect(36, 20, 39, 24), bottom_polygon: rect(36, 10, 39, 14), width_m: 2, length_m: 9 } as Stair],
  } as unknown as Venue;
}

/** Is venue point (x, y) under an upward-facing triangle at height h? */
function covered(g: THREE.BufferGeometry, x: number, y: number, h = 0): boolean {
  const p = g.getAttribute("position");
  const z = -y;
  for (let i = 0; i < p.count; i += 3) {
    const ys = [p.getY(i), p.getY(i + 1), p.getY(i + 2)];
    if (ys.some((v) => Math.abs(v - h) > 1e-4)) continue;
    const [ax, az, bx, bz, cx, cz] = [p.getX(i), p.getZ(i), p.getX(i + 1), p.getZ(i + 1), p.getX(i + 2), p.getZ(i + 2)];
    const d = (bz - cz) * (ax - cx) + (cx - bx) * (az - cz);
    const l1 = ((bz - cz) * (x - cx) + (cx - bx) * (z - cz)) / d;
    const l2 = ((cz - az) * (x - cx) + (ax - cx) * (z - cz)) / d;
    if (l1 >= 0 && l2 >= 0 && 1 - l1 - l2 >= 0) return true;
  }
  return false;
}

describe("polygon subtraction", () => {
  it("keeps a triangle whole when the hole misses it and removes it when the hole covers it", () => {
    expect(subtractConvex([[0, 0], [1, 0], [0, 1]], rect(5, 5, 6, 6))).toHaveLength(1);
    expect(subtractConvex([[0.2, 0.2], [0.8, 0.2], [0.2, 0.8]], rect(0, 0, 1, 1))).toHaveLength(0);
  });
});

describe("floor slabs", () => {
  it("cuts an opening where a stair passes through, and only there", () => {
    const v = tower(2);
    const openings = stairOpenings(v, "F1");
    expect(openings).toHaveLength(2);
    expect(stairOpenings(v, "F0")).toHaveLength(0);
    const slab = slabGeometry(v.floors[1].walkable as Pt[], openings, 0.3);
    // the flight from the ground runs from x 5.45 to 2.45 along y 12.5
    expect(covered(slab.geometry, 4, 12.5)).toBe(false);
    expect(covered(slab.geometry, 56, 12.5)).toBe(false);
    expect(covered(slab.geometry, 30, 12.5)).toBe(true);
    expect(covered(slab.geometry, 4, 14)).toBe(true);
    // the bottom face is there too, and the opening has rims
    expect(covered(slab.geometry, 30, 12.5, -0.3)).toBe(true);
    expect(covered(slab.geometry, 4, 12.5, -0.3)).toBe(false);
    expect(slab.edges.length).toBe(4 + 8);
  });

  it("notches a mezzanine where the stair comes up through its edge", () => {
    const v = hall();
    const slab = slabGeometry(v.floors[1].walkable as Pt[], stairOpenings(v, "F1"), 0.3);
    expect(slab.openings).toHaveLength(1);
    expect(covered(slab.geometry, 37.5, 18)).toBe(false);
    expect(covered(slab.geometry, 37.5, 23)).toBe(true);
    expect(covered(slab.geometry, 20, 18)).toBe(true);
  });
});

describe("guard rails", () => {
  it("runs along a mezzanine's open front, broken by the stair opening, and round the opening", () => {
    const v = hall();
    const mezz = v.floors[1];
    const edges = outerEdges(mezz, floorBelow(v, mezz));
    // three sides sit over the hall's outer walls, the front (y = 15) is open
    expect(edges.open).toHaveLength(1);
    expect(edges.walls).toHaveLength(3);
    const runs = guardRailRuns(v, mezz, edges);
    // the front either side of the opening, and the opening's two long sides
    expect(runs).toHaveLength(4);
    const front = runs.filter(([a, b]) => Math.abs(a[1] - 15) < 1e-6 && Math.abs(b[1] - 15) < 1e-6);
    expect(front).toHaveLength(2);
  });

  it("has no rails on a storey that sits square on the one below", () => {
    const v = tower(3);
    const f = v.floors[2];
    const edges = outerEdges(f, floorBelow(v, f));
    expect(edges.open).toHaveLength(0);
  });
});

describe("outer walls", () => {
  it("splits the wall at a door and bridges it with a lintel", () => {
    const v = tower(1);
    const edges = outerEdges(v.floors[0], null);
    expect(edges.doors).toHaveLength(1);
    // four sides, the south one in two pieces
    expect(edges.walls).toHaveLength(5);
    const south = edges.walls.filter((r) => Math.abs(r.a[1]) < 1e-6 && Math.abs(r.b[1]) < 1e-6);
    expect(south).toHaveLength(2);
    const gap = south.map((r) => [Math.min(r.a[0], r.b[0]), Math.max(r.a[0], r.b[0])]).sort((a, b) => a[0] - b[0]);
    expect(gap[1][0] - gap[0][1]).toBeCloseTo(2.4, 1);
    const tall = outerWallGeometry(edges, { height: 2.4, thickness: 0.18 });
    const low = outerWallGeometry(edges, { height: 1.1, thickness: 0.18 });
    // one box (12 triangles) per wall piece, plus the lintel when the wall is taller than the door
    expect(triangleCount(tall.body)).toBe(12 * 6);
    expect(triangleCount(low.body)).toBe(12 * 5);
  });
});

describe("stairs", () => {
  it("builds a stepped flight with landings and rails on both sides", () => {
    const g = stairGeometry(3, 3.5, 1.2);
    expect(triangleCount(g.body)).toBeGreaterThan(19 * 4);
    expect(triangleCount(g.rails)).toBeGreaterThan(0);
    g.rails.computeBoundingBox();
    // rails stand on both sides of the 1.2 m flight
    expect(g.rails.boundingBox!.min.z).toBeLessThan(-0.6);
    expect(g.rails.boundingBox!.max.z).toBeGreaterThan(0.6);
  });
});

describe("triangle budget", () => {
  it("keeps a 10-storey building light enough for 60 fps", () => {
    const model = buildVenueModel(tower(10), LIGHT_PALETTE);
    const tris = modelTriangles(model);
    disposeModel(model);
    expect(tris).toBeGreaterThan(1000);
    expect(tris).toBeLessThan(25_000);
  });
});
