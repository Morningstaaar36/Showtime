import { describe, expect, it } from "vitest";
import type { Venue } from "@/api/types";
import { CROWD_PEOPLE, itemShape, moveObject, placeItem } from "./dragDrop";

// 40 x 20 m room, counter-clockwise; one 2 m door on the south wall
const venue = {
  mode: "indoor",
  floors: [{
    floor_id: "F0",
    walkable: [[0, 0], [40, 0], [40, 20], [0, 20]],
    exits: [{ id: "door_s1", label: "South door", polygon: [[9, 0.02], [11, 0.02], [11, 0.42], [9, 0.42]], width_m: 2 }],
    obstacles: [{ id: "stage", kind: "stage", polygon: [[15, 16], [25, 16], [25, 20], [15, 20]] }],
    zones: [{ id: "audience", polygon: [[5, 3], [35, 3], [35, 14], [5, 14]], people: 600 }],
  }],
  stairs: [],
  extensions: {},
} as unknown as Venue;
const ids = (p: string) => `${p}_new`;

describe("drag and drop", () => {
  it("drops a door on the nearest wall and names it after that wall", () => {
    const r = placeItem(venue, "F0", "door", 39, 10, "existing", ids);
    expect("error" in r).toBe(false);
    if ("error" in r) return;
    expect(r.name).toBe("East door");
    const south = placeItem(venue, "F0", "door", 30, 1, "existing", ids);
    expect("error" in south ? south.error : south.name).toBe("South door 2");
    expect(r.ops[0]).toMatchObject({ op: "add_exit", floor_id: "F0", id: "exit_new", width_m: 2 });
    expect(r.ops[1]).toMatchObject({ op: "set_annotation", target: "exit_new", change: "existing" });
  });

  it("puts a door dropped anywhere on the venue on its nearest outer wall", () => {
    // in the middle of the floor, a little nearer the south wall: no need to aim at the wall
    const r = placeItem(venue, "F0", "door", 20, 8, "existing", ids);
    if ("error" in r) throw new Error(r.error);
    expect(r.name).toBe("South door 2");
    expect(r.ops[0]).toMatchObject({ op: "add_exit", width_m: 2 });
  });

  it("refuses a door dropped off the venue", () => {
    expect(placeItem(venue, "F0", "door", 60, 10, "existing", ids)).toEqual({ error: "check.door_near_wall" });
  });

  it("makes a crowd area that fits inside the venue, shrinking near walls", () => {
    const r = placeItem(venue, "F0", "crowd", 20, 10, "existing", ids);
    if ("error" in r) throw new Error(r.error);
    expect(r.ops[0]).toMatchObject({ op: "add_zone", people: CROWD_PEOPLE, label: "Crowd area" });
    const corner = itemShape(venue.floors[0], "crowd", 1.5, 1.5);
    expect(corner?.points.every(([x, y]) => x >= 0 && y >= 0)).toBe(true);
    expect(itemShape(venue.floors[0], "crowd", -5, 5)).toBeNull();
  });

  it("lays a fence along the nearest wall", () => {
    const shape = itemShape(venue.floors[0], "fence", 20, 2);
    expect(shape?.points[0][1]).toBeCloseTo(shape?.points[1][1] ?? NaN);
  });

  it("moves features by whole half metres and ignores tiny drags", () => {
    expect(moveObject(venue, "stage", "stage", [20, 18], [22.2, 16.9])).toMatchObject({ ops: [{ op: "move", target: "stage", dx: 2, dy: -1 }] });
    expect(moveObject(venue, "stage", "stage", [20, 18], [20.1, 18.1])).toBeNull();
  });

  it("slides a door along its wall, and rebuilds it in place on another wall", () => {
    const slide = moveObject(venue, "exit", "door_s1", [10, 0.2], [20, 0.5]);
    if (!slide || "error" in slide) throw new Error("expected a move");
    expect(slide.ops).toEqual([{ op: "move", target: "door_s1", dx: 10, dy: 0 }]);
    const turn = moveObject(venue, "exit", "door_s1", [10, 0.2], [39.5, 10]);
    if (!turn || "error" in turn) throw new Error("expected a move");
    expect(turn.ops.map((o) => o.op)).toEqual(["remove_exit", "add_exit"]);
    expect(turn.ops[1]).toMatchObject({ id: "door_s1", label: "South door", index: 0 });
  });
});
