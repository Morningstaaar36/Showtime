import * as THREE from "three";
import { describe, expect, it } from "vitest";
import type { Floor, Obstacle, Pt, Stair, Venue } from "@/api/types";
import { LIGHT_PALETTE } from "../palette";
import { labelledIds } from "../labels";
import { buildVenueModel, disposeModel } from "./building";
import { facadeGeometry, facadeLevels, roofGeometry, SILL_M } from "./facade";
import { fixtureOf, isStairVoid, isStairwellWall, kitchenGeometry, liftGeometry, tableMatrix, tablePlacements, tableUnitGeometry } from "./fixtures";
import { outerEdges } from "./floor";

const rect = (x0: number, y0: number, x1: number, y1: number): Pt[] => [[x0, y0], [x1, y0], [x1, y1], [x0, y1]];
const ob = (id: string, kind: string, label: string | null, polygon: Pt[] = rect(0, 0, 1, 1), height_m: number | null = null) =>
  ({ id, kind, label, polygon, height_m, line: null }) as Obstacle;

function bounds(g: THREE.BufferGeometry): THREE.Box3 {
  g.computeBoundingBox();
  return g.boundingBox!;
}
const tris = (g: THREE.BufferGeometry) => (g.getAttribute("position")?.count ?? 0) / 3;

/** A restaurant tower like the generated one: a stair core with walls round it, a lift, a kitchen,
 * toilets and rows of tables on every floor, a front door on the ground. */
function restaurant(storeys: number): Venue {
  const floors: Floor[] = [];
  const stairs: Stair[] = [];
  for (let i = 0; i < storeys; i++) {
    const tables = Array.from({ length: 6 }, (_, k) => ob(`f${i}_table_${k}`, "seating", "Table", rect(10 + 2.4 * k, 8, 10.9 + 2.4 * k, 8.9), 0.75));
    floors.push({
      floor_id: `F${i}`, name: null, elevation_m: i * 3.5, walkable: rect(0, 0, 30, 16), zones: [],
      obstacles: [
        ob(`f${i}_stairwell_1`, "wall", "Stairwell wall", [[0.5, 4], [4.5, 4], [4.5, 4.2], [0.7, 4.2], [0.7, 11.8], [4.5, 11.8], [4.5, 12], [0.5, 12]], 3.2),
        ob(`f${i}_lift_2`, "other", "Lift (not used in a fire)", rect(5, 4, 7, 6), 3.2),
        ob(`f${i}_kitchen_3`, "other", "Kitchen", rect(24, 0.3, 29.7, 15.7), 3.2),
        ob(`f${i}_toilets_4`, "booth", "Toilets", rect(20, 12, 23.5, 15.7), 3.2),
        ...tables,
      ],
      exits: i === 0 ? [{ id: "front", polygon: rect(14, 0.02, 16, 0.42), width_m: 2, blocked: false, label: "Front door" }] : [],
    } as unknown as Floor);
    if (i > 0) {
      stairs.push({ id: `s${i}`, from_floor: `F${i}`, to_floor: `F${i - 1}`, top_polygon: rect(1, 5, 3, 7), bottom_polygon: rect(1, 9, 3, 11),
        width_m: 1.2, length_m: 6 } as Stair);
    }
  }
  return { venue_id: "r", name: "Restaurant", description: "", mode: "indoor", floors, stairs, routes: [], stage: null } as unknown as Venue;
}

describe("stair voids and stairwell walls", () => {
  it("cuts out a stair's footprint but keeps the walls round a stairwell", () => {
    expect(isStairVoid(ob("stair_structure", "other", "Stair structure"))).toBe(true);
    expect(isStairVoid(ob("f1_stairwell_9", "wall", "Stairwell wall"))).toBe(false);
    expect(isStairwellWall(ob("f1_stairwell_9", "wall", "Stairwell wall"))).toBe(true);
    expect(isStairwellWall(ob("w", "wall", "Wall"))).toBe(false);
  });
});

describe("fixtures by label", () => {
  it("names kitchens, washrooms, lifts, tables and counters, and nothing else", () => {
    expect(fixtureOf(ob("a", "other", "Kitchen"))).toBe("kitchen");
    expect(fixtureOf(ob("b", "booth", "Toilets"))).toBe("toilets");
    expect(fixtureOf(ob("c", "other", "Lift (not used in a fire)"))).toBe("lift");
    expect(fixtureOf(ob("d", "seating", "Table"))).toBe("table");
    expect(fixtureOf(ob("e", "bar", "Service counter"))).toBe("counter");
    expect(fixtureOf(ob("f", "other", "Escalator"))).toBeNull();
    expect(fixtureOf(ob("g", "other", "Atrium (open to below)"))).toBeNull();
    expect(fixtureOf(ob("h", "booth", "Bar"))).toBeNull();
    expect(fixtureOf(ob("i", "wall", "Kitchen wall"))).toBeNull();
    expect(fixtureOf(ob("j", "seating", null))).toBeNull();
  });

  it("never gives a table a label of its own", () => {
    const v = restaurant(1);
    const ids = labelledIds(v, "F0", null, { exits: 1, zones: 1, features: 50 }, 0);
    expect(ids).not.toBeNull();
    expect([...ids!].some((id) => id.includes("table"))).toBe(false);
    expect(ids!.has("f0_kitchen_3")).toBe(true);
  });
});

describe("fixture meshes", () => {
  it("places each table on its footprint, turned with it", () => {
    const turned = ob("t", "seating", "Table", [[0, 0], [0.9, 0.9], [0, 1.8], [-0.9, 0.9]], 0.75);
    const [p] = tablePlacements([turned, ob("k", "other", "Kitchen")]);
    expect(p.x).toBeCloseTo(0, 6);
    expect(p.y).toBeCloseTo(0.9, 6);
    expect(p.angle).toBeCloseTo(Math.PI / 4, 6);
    expect(p.w).toBeCloseTo(0.9 * Math.SQRT2, 6);
    const unit = tableUnitGeometry();
    const top = bounds(unit.table.clone().applyMatrix4(tableMatrix(p)));
    expect(top.max.y).toBeCloseTo(0.75, 3);
    expect(top.min.x).toBeCloseTo(-0.9, 2);
    expect(top.max.z).toBeCloseTo(-0, 2);
    // chairs stand round the table, lower than its top's edge
    expect(bounds(unit.chairs).max.x).toBeGreaterThan(0.9);
  });

  it("builds a kitchen as walls, counters with an island, and a floor; a lift with doors", () => {
    const k = kitchenGeometry(rect(0, 0, 6, 10), 3);
    expect(bounds(k.walls).max.y).toBeCloseTo(3);
    expect(bounds(k.counters).max.y).toBeCloseTo(0.9);
    // four wall counters and an island
    expect(tris(k.counters)).toBe(12 * 5);
    expect(tris(k.floor)).toBeGreaterThan(0);
    const l = liftGeometry(rect(0, 0, 2, 2), 3.2, [1, 10]);
    expect(bounds(l.shaft).max.y).toBeCloseTo(3.2);
    // doors on the north side (venue y = 2 -> world z = -2), facing the floor's middle
    expect(bounds(l.doors).min.z).toBeLessThan(-2);
  });
});

describe("facade", () => {
  it("has a solid sill, a glass band and a spandrel up to the slab, and a head over the door", () => {
    const v = restaurant(2);
    const edges = outerEdges(v.floors[0], null);
    const f = facadeGeometry(edges, { height: 3.2, thickness: 0.18 });
    const lv = facadeLevels(3.2);
    expect(lv.sill).toBe(SILL_M);
    expect(lv.windowTop).toBeGreaterThan(SILL_M + 1);
    expect(lv.windowTop).toBeLessThan(3.2);
    expect(bounds(f.sill).min.y).toBeCloseTo(0);
    expect(bounds(f.sill).max.y).toBeCloseTo(SILL_M);
    // four sides of a rectangle, each with glass, spandrel and frames
    expect(f.sides).toHaveLength(4);
    for (const s of f.sides) {
      expect(bounds(s.glass).min.y).toBeCloseTo(SILL_M);
      expect(bounds(s.spandrel).max.y).toBeCloseTo(3.2);
      expect(tris(s.frame)).toBeGreaterThan(0);
    }
    // the south side holds the door: under the door head nothing stands in the opening
    const south = f.sides.find((s) => s.normal[1] < -0.9)!;
    expect(south.mid[1]).toBeCloseTo(0, 6);
    const pos = f.sill.getAttribute("position");
    for (let i = 0; i < pos.count; i++) {
      const x = pos.getX(i), z = pos.getZ(i);
      if (z > -0.01 && z < 0.2) expect(x <= 14.1 || x >= 15.9).toBe(true);
    }
    // one side only when not split
    expect(facadeGeometry(edges, { height: 3.2, thickness: 0.18 }, false).sides).toHaveLength(1);
  });

  it("roofs only what no floor above covers", () => {
    const v = restaurant(3);
    expect(roofGeometry(v, v.floors[0], 3.5, 0.3, 0.18)).toBeNull();
    const top = roofGeometry(v, v.floors[2], 3.2, 0.3, 0.18)!;
    expect(bounds(top.deck).max.y).toBeCloseTo(3.2);
    expect(bounds(top.parapet).max.y).toBeGreaterThan(3.2);
  });
});

describe("restaurant export", () => {
  it("keeps stairwell walls, roofs the top, and bakes the tables into one mesh per floor", () => {
    const model = buildVenueModel(restaurant(3), LIGHT_PALETTE);
    const names: string[] = [];
    model.traverse((o) => { if (o instanceof THREE.Mesh) names.push(o.name); });
    disposeModel(model);
    expect(names.filter((n) => n === "Stairwell wall")).toHaveLength(3);
    expect(names.filter((n) => n === "Roof")).toHaveLength(1);
    expect(names.filter((n) => n === "Tables")).toHaveLength(3);
    expect(names).not.toContain("Table");
    expect(names).toEqual(expect.arrayContaining(["Facade sill", "Facade glass", "Facade spandrel", "Window frames", "Slab edge",
      "Kitchen counters", "Lift (not used in a fire)", "Toilets", "Chairs", "Parapet"]));
    expect(names).not.toContain("Outer walls");
  });
});
