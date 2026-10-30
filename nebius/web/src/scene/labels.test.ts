import { describe, expect, it } from "vitest";
import type { Venue } from "@/api/types";
import { labelledIds } from "./labels";

const sq = (x: number, s = 1): [number, number][] => [[x, 0], [x + s, 0], [x + s, s], [x, s]];
const floor = (id: string, elev: number, n: { exits?: number; zones?: number; features?: number } = {}) => ({
  floor_id: id, name: null, elevation_m: elev, walkable: [[0, 0], [500, 0], [500, 100], [0, 100]],
  exits: Array.from({ length: n.exits ?? 1 }, (_, i) => ({ id: `${id}e${i}`, polygon: sq(i), width_m: 1 + i })),
  zones: Array.from({ length: n.zones ?? 1 }, (_, i) => ({ id: `${id}z${i}`, polygon: sq(i), people: i * 10 })),
  obstacles: [
    ...Array.from({ length: n.features ?? 0 }, (_, i) => ({ id: `${id}o${i}`, kind: "booth", polygon: sq(i, 1 + i), label: null })),
    { id: `${id}w`, kind: "wall", polygon: sq(0), label: null },
    { id: `${id}b`, kind: "other", polygon: sq(0, 50), label: "Building 12" },
  ],
});
const venue = (floors: ReturnType<typeof floor>[], stairs: { id: string; from_floor: string; to_floor: string }[] = []) =>
  ({ floors, stairs, routes: [] } as unknown as Venue);

describe("3D labels", () => {
  it("labels everything on a small one-floor venue", () => {
    expect(labelledIds(venue([floor("F0", 0)]), "all", null)).toBeNull();
  });
  it("names only the doors and the focus floor's stairs when three floors are stacked", () => {
    const v = venue([floor("F1", 3.5), floor("F0", 0), floor("F2", 7)], [{ id: "s1", from_floor: "F1", to_floor: "F0" }]);
    // seen whole, room and area names would float over the storeys above them
    expect([...labelledIds(v, "all", null)!].sort()).toEqual(["F0e0", "F1e0", "F2e0", "s1"]);
    expect(labelledIds(v, "all", "F2")!.has("F2z0")).toBe(false);
    expect(labelledIds(v, "all", "F2")!.has("s1")).toBe(false);
    // a hall and its mezzanine read fine together
    expect(labelledIds(venue([floor("F0", 0), floor("F1", 3.5)]), "all", null)).toBeNull();
    // spread apart, the same: the floors' names would still overlap
    expect(labelledIds(v, "exploded", "F2")!.has("F2z0")).toBe(true);
    expect(labelledIds(v, "exploded", "F2")!.has("F0z0")).toBe(false);
    expect(labelledIds(venue([floor("F0", 0), floor("F1", 3.5)]), "exploded", null)).toBeNull();
  });
  it("keeps the widest exits, fullest areas and largest features on a big site", () => {
    const v = venue([floor("F0", 0, { exits: 40, zones: 30, features: 20 })]);
    const ids = labelledIds(v, "all", null, { exits: 3, zones: 2, features: 1 })!;
    expect([...ids].sort()).toEqual(["F0e37", "F0e38", "F0e39", "F0o19", "F0z28", "F0z29"]);
  });
  it("counts only the floor shown alone", () => {
    const v = venue([floor("F0", 0, { exits: 45 }), floor("F1", 3.5)]);
    expect(labelledIds(v, "F1", null)).toBeNull();
    expect(labelledIds(v, "F0", null)!.size).toBeLessThan(47);
  });
});
