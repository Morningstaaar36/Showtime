import { describe, expect, it } from "vitest";
import type { Venue } from "@/api/types";
import { buildOptionsOf, clickStep, dropLastPoint, finishStep, roomStep, stairConnects, stairWell, stairStep } from "./buildTools";
import { editorDefaultsOf } from "./editorDefaults";

const square = (s: number): [number, number][] => [[0, 0], [s, 0], [s, s], [0, s]];
const floor = (id: string, elevation: number, extra: Partial<Venue["floors"][number]> = {}) => ({
  floor_id: id, name: null, elevation_m: elevation, walkable: square(20), obstacles: [], exits: [], zones: [], ...extra,
});
const venue = (floors: Venue["floors"][number][]): Venue => ({
  schema_version: 1, venue_id: "v", name: "Test", description: null, mode: "indoor", event_kind: null,
  floors: floors as Venue["floors"], stairs: [], routes: [], stage: null, location: null, rules_profile: "generic", extensions: {},
} as unknown as Venue);
// the options before the organizer changes any, with the sizes used until the settings load
const O = buildOptionsOf(editorDefaultsOf({}));
const wall = { id: "w1", kind: "wall" as const, polygon: [[9.9, 2], [10.1, 2], [10.1, 18], [9.9, 18]] as [number, number][],
  height_m: null, label: null, line: [[10, 2], [10, 18]] as [number, number][] };

describe("walls and routes", () => {
  it("collects corners, snapping wall corners to the outline", () => {
    const v = venue([floor("F0", 0)]);
    const a = clickStep("wall", v, "F0", [], 0.2, 5, O);
    expect(a).toEqual({ kind: "draft", draft: [[0, 5]] });
    const b = clickStep("wall", v, "F0", [[0, 5]], 8, 5, O);
    expect(b).toEqual({ kind: "draft", draft: [[0, 5], [8, 5]] });
    expect(finishStep("wall", "F0", [[0, 5], [8, 5]], O)).toMatchObject({
      kind: "ops", ops: [{ op: "add_wall", floor_id: "F0", points: [[0, 5], [8, 5]], thickness_m: 0.2 }], message: "Added a wall",
    });
  });
  it("refuses to finish with one corner", () => {
    expect(finishStep("wall", "F0", [[1, 1]], O)).toEqual({ kind: "error", error: "wall_short" });
    expect(finishStep("route", "F0", [], O)).toEqual({ kind: "error", error: "route_short" });
    expect(finishStep("door", "F0", [], O)).toBeNull();
  });
  it("names the route and keeps the points unsnapped", () => {
    const v = venue([floor("F0", 0)]);
    expect(clickStep("route", v, "F0", [], 0.3, 5, O)).toEqual({ kind: "draft", draft: [[0.3, 5]] });
    const done = finishStep("route", "F0", [[1, 1], [10, 1]], { ...O, routeLabel: "Parade", routeWidth: 6 });
    expect(done).toMatchObject({ kind: "ops", ops: [{ op: "add_route", points: [[1, 1], [10, 1]], width_m: 6, label: "Parade" }], message: "Added Parade" });
    expect(finishStep("route", "F0", [[1, 1], [10, 1]], O)).toMatchObject({ message: "Added March route" });
  });
  it("removes the last corner", () => {
    expect(dropLastPoint([[0, 0], [1, 1]])).toEqual([[0, 0]]);
    expect(dropLastPoint([])).toEqual([]);
  });
});

describe("doors", () => {
  it("cuts a door in the inner wall next to the click", () => {
    const v = venue([floor("F0", 0, { obstacles: [wall] as never })]);
    expect(clickStep("door", v, "F0", [], 10.4, 8, O)).toMatchObject({ kind: "ops", ops: [{ op: "add_door", wall_id: "w1", x: 10, y: 8, width_m: 1 }] });
  });
  it("explains a click on the outer wall or in the open", () => {
    const v = venue([floor("F0", 0)]);
    expect(clickStep("door", v, "F0", [], 0.2, 8, O)).toEqual({ kind: "error", error: "door_outer_wall" });
    expect(clickStep("door", v, "F0", [], 5, 8, O)).toEqual({ kind: "error", error: "door_no_wall" });
  });
});

describe("rooms", () => {
  it("takes two corners in any order", () => {
    const v = venue([floor("F0", 0)]);
    const first = clickStep("room", v, "F0", [], 8, 9, O);
    expect(first).toEqual({ kind: "draft", draft: [[8, 9]] });
    const done = clickStep("room", v, "F0", [[8, 9]], 3, 4, { ...O, roomLabel: "Ward A", roomPeople: 12 });
    expect(done).toMatchObject({
      kind: "ops", message: "Added Ward A",
      ops: [{ op: "add_room", floor_id: "F0", x: 3, y: 4, width_m: 5, depth_m: 5, door_wall: "south", door_width_m: 1, people: 12, label: "Ward A" }],
    });
  });
  it("rejects a room that is too small or a door wider than its side", () => {
    expect(roomStep("F0", { x: 0, y: 0, width_m: 1, depth_m: 4 }, O)).toEqual({ kind: "error", error: "room_too_small" });
    expect(roomStep("F0", { x: 0, y: 0, width_m: 2, depth_m: 4 }, { ...O, roomDoorWidth: 2 })).toEqual({ kind: "error", error: "room_door_wide" });
    expect(roomStep("F0", { x: 0, y: 0, width_m: 2, depth_m: 4 }, O)).toMatchObject({ message: "Added Room" });
  });
});

describe("stairs", () => {
  it("joins the edit floor to the one below, or the ground floor to the one above", () => {
    const v = venue([floor("F0", 0), floor("F1", 3.5), floor("F2", 7)]);
    expect(stairStep(v, "F2", 5, 5, O)).toMatchObject({ kind: "ops", ops: [{ op: "add_stair", from_floor: "F2", to_floor: "F1", x: 5, y: 5, width_m: 1.5, run_m: 6, direction: "north" }] });
    expect(stairStep(v, "F0", 5, 5, O)).toMatchObject({ ops: [{ from_floor: "F1", to_floor: "F0" }] });
    expect(clickStep("stair", v, "F1", [], 4, 4, { ...O, stairDirection: "east" })).toMatchObject({ ops: [{ from_floor: "F1", to_floor: "F0", direction: "east" }] });
  });
  it("asks for a second floor first", () => {
    expect(stairStep(venue([floor("F0", 0)]), "F0", 5, 5, O)).toEqual({ kind: "error", error: "stair_needs_floor" });
  });
  it("draws the stairwell centred on the click, like the server", () => {
    expect(stairWell(5, 5, "north", 2, 6)).toEqual([[6, 2], [6, 8], [4, 8], [4, 2]]);
    const v = venue([floor("F0", 0), floor("F1", 3.5)]);
    expect(stairConnects(v, "F1", (id) => id.toLowerCase())).toEqual({ from: "f1", to: "f0" });
    expect(stairConnects(venue([floor("F0", 0)]), "F0", String)).toBeNull();
  });
});
