import { describe, expect, it } from "vitest";
import type { Venue } from "@/api/types";
import type { EventKindInfo } from "./eventKinds";
import { groupsOf, kindsLeft, restPercent, routesOn, rowsOf, usualMixOps } from "./zoneProfile";

const sq = (x: number): [number, number][] => [[x, 0], [x + 4, 0], [x + 4, 4], [x, 4]];
const venue = {
  schema_version: 1, venue_id: "v", name: "Ward", mode: "indoor", event_kind: "hospital",
  floors: [{ floor_id: "F0", name: null, elevation_m: 0, walkable: [[0, 0], [30, 0], [30, 10], [0, 10]], obstacles: [], exits: [],
             zones: [
               { id: "a", polygon: sq(0), people: 20, groups: [], pre_movement_s: null, route_id: null },
               { id: "b", polygon: sq(5), people: 10, groups: [{ kind: "bed", share: 0.25 }], pre_movement_s: null, route_id: null },
               { id: "out", polygon: sq(10), people: 0, groups: [], pre_movement_s: null, route_id: null },
             ] }],
  stairs: [], routes: [{ id: "r1", floor_id: "F0", points: [[0, 0], [5, 5]] }, { id: "r2", floor_id: "F1", points: [[0, 0], [1, 1]] }],
} as unknown as Venue;
const kind = (groups: EventKindInfo["default_groups"], pre: number | null = null): EventKindInfo => ({
  id: "hospital", label: "Hospital", description: "", default_groups: groups, default_pre_movement_s: pre, interior: "rooms",
});

describe("people mix rows", () => {
  it("shows shares as whole percents and drops general adults", () => {
    expect(rowsOf([{ kind: "bed", share: 0.25 }, { kind: "general", share: 0.5 }, { kind: "staff", share: 0 }])).toEqual([{ kind: "bed", percent: "25" }]);
    expect(rowsOf(null)).toEqual([]);
  });
  it("saves percents as shares and refuses more than 100%", () => {
    expect(groupsOf([{ kind: "bed", percent: "25" }, { kind: "staff", percent: "10" }])).toEqual({ groups: [{ kind: "bed", share: 0.25 }, { kind: "staff", share: 0.1 }] });
    expect(groupsOf([{ kind: "bed", percent: "70" }, { kind: "staff", percent: "40" }])).toEqual({ error: "over" });
    expect(groupsOf([{ kind: "bed", percent: "" }])).toEqual({ error: "invalid" });
    expect(groupsOf([{ kind: "bed", percent: "0" }])).toEqual({ groups: [] });
  });
  it("counts the general adults left and the kinds still to add", () => {
    expect(restPercent([{ kind: "bed", percent: "25" }, { kind: "child", percent: "10" }])).toBe(65);
    expect(restPercent([{ kind: "bed", percent: "80" }, { kind: "child", percent: "40" }])).toBe(0);
    expect(kindsLeft([{ kind: "bed", percent: "1" }])).toEqual(["elderly", "child", "wheelchair", "staff"]);
  });
});

describe("usual mix for every area", () => {
  it("changes only areas with people that differ", () => {
    const ops = usualMixOps(venue, kind([{ kind: "bed", share: 0.25 }]));
    expect(ops).toEqual([{ op: "set_zone_profile", zone_id: "a", groups: [{ kind: "bed", share: 0.25 }] }]);
  });
  it("adds the usual start delay when one is cited", () => {
    const ops = usualMixOps(venue, kind([], 120));
    expect(ops).toEqual([
      { op: "set_zone_profile", zone_id: "a", pre_movement_s: 120 },
      { op: "set_zone_profile", zone_id: "b", pre_movement_s: 120 },
    ]);
  });
  it("does nothing for a kind with no usual mix", () => {
    expect(usualMixOps(venue, kind([]))).toEqual([]);
  });
  it("lists the routes on a floor", () => {
    expect(routesOn(venue, "F0").map((r) => r.id)).toEqual(["r1"]);
  });
});
