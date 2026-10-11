import { describe, expect, it } from "vitest";
import type { PatchOpIn, Venue } from "@/api/types";
import { annotateOp, annotationOf, isProposed, lockConflicts, lockedIds } from "@/lib/annotations";
import { diffVenues } from "@/lib/venueDiff";
import { planFreshness } from "@/lib/evidence";

const sq = [[0, 0], [1, 0], [1, 1], [0, 1]];
const venue = {
  floors: [{
    floor_id: "F0",
    exits: [{ id: "door_s1", polygon: sq, width_m: 2 }, { id: "door_e1", polygon: sq, width_m: 2 }],
    obstacles: [{ id: "stage", kind: "stage", polygon: sq }, { id: "bar", kind: "bar", polygon: sq }],
    zones: [{ id: "audience", polygon: sq, people: 100 }],
  }],
  stairs: [],
  extensions: {
    plan_annotations: { schema_version: 1, objects: { stage: { locked: true }, door_e1: { change: "proposed" } } },
    scene_metadata: { schema_version: 1, objects: { door_s1: { basis: "measured", source: "Tape" } } },
  },
} as unknown as Venue;

const op = (o: Record<string, unknown>) => o as unknown as PatchOpIn;

describe("annotations", () => {
  it("reads locks, change status and provenance", () => {
    expect(lockedIds(venue)).toEqual(new Set(["stage"]));
    expect(isProposed(venue, "door_e1")).toBe(true);
    expect(isProposed(venue, "door_s1")).toBe(false);
    expect(annotationOf(venue, "door_s1").provenance).toEqual({ basis: "measured", source: "Tape" });
    expect(annotationOf(venue, "bar")).toEqual({ locked: false, change: null, provenance: { basis: "unknown" } });
  });

  it("a venue without annotations has none", () => {
    const bare = { ...venue, extensions: {} } as Venue;
    expect(lockedIds(bare).size).toBe(0);
    expect(annotationOf(bare, "stage").locked).toBe(false);
  });

  it("flags proposal ops that touch locked objects, including stage parameters", () => {
    const ops = [
      op({ op: "move", target: "stage", dx: 1, dy: 0 }),
      op({ op: "move", target: "bar", dx: 1, dy: 0 }),
      op({ op: "set_stage_param", param: "legs", value: 8 }),
      op({ op: "add_exit", floor_id: "F0", id: "stage", width_m: 2 }), // adding is not changing
    ];
    expect(lockConflicts(venue, ops)).toEqual([{ id: "stage", op: "move" }, { id: "stage", op: "set_stage_param" }]);
  });

  it("the organizer's own lock changes are never conflicts", () => {
    expect(lockConflicts(venue, [annotateOp("stage", { locked: false })])).toEqual([]);
  });
});

describe("diffVenues", () => {
  it("lists added, changed and removed objects", () => {
    const after = structuredClone(venue) as Venue;
    after.floors[0].exits[0].width_m = 3;
    after.floors[0].obstacles = after.floors[0].obstacles.filter((o) => o.id !== "bar");
    after.floors[0].exits.push({ id: "gate_n", polygon: sq, width_m: 4 } as never);
    const d = diffVenues(venue, after).map((c) => `${c.kind}:${c.id}`);
    expect(d.sort()).toEqual(["added:gate_n", "changed:door_s1", "removed:bar"]);
  });

  it("identical venues have no changes", () => {
    expect(diffVenues(venue, structuredClone(venue) as Venue)).toEqual([]);
  });
});

describe("planFreshness", () => {
  it("separates tested, accepted, edited and untested venues", () => {
    expect(planFreshness({ currentHash: "a", testedHash: "a", fixedHash: "b" })).toBe("current_before");
    expect(planFreshness({ currentHash: "b", testedHash: "a", fixedHash: "b" })).toBe("current_after");
    expect(planFreshness({ currentHash: "c", testedHash: "a", fixedHash: "b" })).toBe("stale");
    expect(planFreshness({ currentHash: "c", testedHash: "a" })).toBe("stale");
    expect(planFreshness({ currentHash: "a", testedHash: null })).toBe("none");
  });
});
