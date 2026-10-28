import { describe, expect, it } from "vitest";
import type { Venue } from "@/api/types";
import {
  addFloorOp, addRouteOp, addStairOp, addWallOp, defaultInterior, floorLevels, levelName, levelTag, nearestWall,
  nextFloorId, normalizeGroups, planDoor, planRoom, removeFloorOp, removeStairOp, resolveEditFloor, roomFromCorners,
  setEventKindOp, snapPoint, stairEnds, zoneProfileOp,
} from "./venueOps";

const square = (s: number): [number, number][] => [[0, 0], [s, 0], [s, s], [0, s]];
const floor = (id: string, elevation: number, extra: Partial<Venue["floors"][number]> = {}) => ({
  floor_id: id, name: null, elevation_m: elevation, walkable: square(20), obstacles: [], exits: [], zones: [], ...extra,
});
const venue = (floors: Venue["floors"][number][]): Venue => ({
  schema_version: 1, venue_id: "v", name: "Test", description: null, mode: "indoor", event_kind: null,
  floors: floors as Venue["floors"], stairs: [], routes: [], stage: null, location: null, rules_profile: "generic", extensions: {},
} as unknown as Venue);

const wall = { id: "w1", kind: "wall" as const, polygon: [[9.9, 2], [10.1, 2], [10.1, 18], [9.9, 18]] as [number, number][],
  height_m: null, label: null, line: [[10, 2], [10, 18]] as [number, number][] };

describe("floor labels and ids", () => {
  it("numbers storeys from the ground floor and names them", () => {
    const v = venue([floor("F2", 7), floor("F0", 0), floor("B", -3.5), floor("F1", 3.5)]);
    const l = floorLevels(v);
    expect([l.get("B"), l.get("F0"), l.get("F1"), l.get("F2")]).toEqual([-1, 0, 1, 2]);
    expect([-1, 0, 2].map(levelName)).toEqual(["Basement 1", "Ground floor", "Floor 2"]);
    expect([-1, 0, 2].map(levelTag)).toEqual(["B1", "G", "2"]);
  });
  it("falls back to the lowest floor when the edit floor is gone", () => {
    const v = venue([floor("F1", 3.5), floor("F0", 0)]);
    expect(resolveEditFloor(v, "F9")).toBe("F0");
    expect(resolveEditFloor(v, "F1")).toBe("F1");
    expect(resolveEditFloor(v, null)).toBe("F0");
  });
  it("adds a floor with a free id and a default name", () => {
    const v = venue([floor("F0", 0), floor("F1", 3.5)]);
    expect(nextFloorId(v)).toBe("F2");
    expect(addFloorOp(v)).toEqual({ op: "add_floor", floor_id: "F2", name: "Floor 2", height_m: 3.5, copy_walls: true });
    expect(addFloorOp(v, { name: " Roof ", height_m: 4.25, copy_walls: false }))
      .toEqual({ op: "add_floor", floor_id: "F2", name: "Roof", height_m: 4.25, copy_walls: false });
    expect(removeFloorOp("F1")).toEqual({ op: "remove_floor", floor_id: "F1" });
  });
});

describe("stairs", () => {
  it("connects down from an upper floor, and up from the lowest one", () => {
    const v = venue([floor("F0", 0), floor("F1", 3.5), floor("F2", 7)]);
    expect(stairEnds(v, "F2")).toEqual({ from_floor: "F2", to_floor: "F1" });
    expect(stairEnds(v, "F0")).toEqual({ from_floor: "F1", to_floor: "F0" });
    expect(stairEnds(venue([floor("F0", 0)]), "F0")).toBeNull();
  });
  it("builds add_stair with the contract fields", () => {
    const v = venue([floor("F0", 0), floor("F1", 3.5)]);
    expect(addStairOp(v, "F1", 4.123, 5, { direction: "east" })).toEqual({
      op: "add_stair", from_floor: "F1", to_floor: "F0", x: 4.12, y: 5, width_m: 1.5, run_m: 6, direction: "east",
    });
    expect(addStairOp(venue([floor("F0", 0)]), "F0", 1, 1)).toBeNull();
    expect(removeStairOp("s1")).toEqual({ op: "remove_stair", stair_id: "s1" });
  });
});

describe("walls and doors", () => {
  it("drops the doubled last point of a double-click", () => {
    expect(addWallOp("F0", [[0, 0], [5, 0], [5, 0.01]])).toEqual({ op: "add_wall", floor_id: "F0", points: [[0, 0], [5, 0]], thickness_m: 0.2 });
    expect(addWallOp("F0", [[1, 1], [1, 1]])).toBeNull();
  });
  it("finds the nearest inner wall and cuts the door there", () => {
    const f = floor("F0", 0, { obstacles: [wall] });
    expect(nearestWall(f, 9, 7)?.point).toEqual([10, 7]);
    const plan = planDoor(f, 9.4, 7.333, 1.2);
    expect(plan).toEqual({ op: { op: "add_door", floor_id: "F0", wall_id: "w1", x: 10, y: 7.33, width_m: 1.2 }, at: [10, 7.33], wallId: "w1" });
  });
  it("explains a click that is not on an inner wall", () => {
    const f = floor("F0", 0, { obstacles: [wall] });
    expect(planDoor(f, 5, 7)).toEqual({ error: "door_no_wall" });
    expect(planDoor(f, 0.5, 7)).toEqual({ error: "door_outer_wall" });
    expect(planDoor(f, 10, 7, 20)).toEqual({ error: "door_wall_short" });
  });
  it("snaps to corners first, then onto lines", () => {
    const f = floor("F0", 0, { obstacles: [wall] });
    expect(snapPoint(f, 0.3, 19.8)).toEqual([0, 20]);
    expect(snapPoint(f, 10.2, 9)).toEqual([10, 9]);
    expect(snapPoint(f, 5, 5)).toEqual([5, 5]);
  });
});

describe("rooms", () => {
  it("turns two corners into the south-west corner and a size", () => {
    expect(roomFromCorners([8, 9], [2, 3])).toEqual({ x: 2, y: 3, width_m: 6, depth_m: 6 });
  });
  it("builds add_room and adds people only when given", () => {
    const r = { x: 2, y: 3, width_m: 6, depth_m: 4 };
    expect(planRoom("F1", r)).toEqual({ op: { op: "add_room", floor_id: "F1", x: 2, y: 3, width_m: 6, depth_m: 4, door_wall: "south", door_width_m: 1 } });
    expect(planRoom("F1", r, { door_wall: "west", people: 12.4, label: "Ward A", groups: [{ kind: "bed", share: 0.5 }] })).toEqual({
      op: { op: "add_room", floor_id: "F1", x: 2, y: 3, width_m: 6, depth_m: 4, door_wall: "west", door_width_m: 1, people: 12, label: "Ward A", groups: [{ kind: "bed", share: 0.5 }] },
    });
  });
  it("refuses rooms too small for a door", () => {
    expect(planRoom("F0", { x: 0, y: 0, width_m: 1, depth_m: 5 })).toEqual({ error: "room_too_small" });
    expect(planRoom("F0", { x: 0, y: 0, width_m: 2, depth_m: 5 }, { door_width_m: 1.9 })).toEqual({ error: "room_door_wide" });
  });
});

describe("people profile, routes and event kind", () => {
  it("keeps shares within 100%", () => {
    expect(normalizeGroups([{ kind: "elderly", share: 0.304 }, { kind: "child", share: 0 }])).toEqual([{ kind: "elderly", share: 0.3 }]);
    expect(normalizeGroups([{ kind: "elderly", share: 0.7 }, { kind: "child", share: 0.4 }])).toBeNull();
    expect(normalizeGroups([{ kind: "bed", share: -0.1 }])).toBeNull();
  });
  it("sends only the changed profile fields, and null to clear", () => {
    expect(zoneProfileOp("z1", { groups: [] })).toEqual({ op: "set_zone_profile", zone_id: "z1", groups: [] });
    expect(zoneProfileOp("z1", { pre_movement_s: 90.4 })).toEqual({ op: "set_zone_profile", zone_id: "z1", pre_movement_s: 90 });
    expect(zoneProfileOp("z1", { pre_movement_s: null, route_id: null })).toEqual({ op: "set_zone_profile", zone_id: "z1", pre_movement_s: null, route_id: null });
  });
  it("builds routes in walking order", () => {
    expect(addRouteOp("F0", [[0, 0], [10, 0], [10, 0], [10, 10]], { label: "March", width_m: 6 }))
      .toEqual({ op: "add_route", floor_id: "F0", points: [[0, 0], [10, 0], [10, 10]], width_m: 6, label: "March" });
    expect(addRouteOp("F0", [[0, 0]])).toBeNull();
    expect(setEventKindOp("march")).toEqual({ op: "set_event_kind", event_kind: "march" });
    expect(setEventKindOp(null)).toEqual({ op: "set_event_kind", event_kind: null });
  });
});

describe("map import", () => {
  it("defaults to rooms for care, school, office and housing", () => {
    expect(defaultInterior("hospital")).toBe("rooms");
    expect(defaultInterior("mall")).toBe("open");
    expect(defaultInterior(null)).toBe("open");
  });
});
