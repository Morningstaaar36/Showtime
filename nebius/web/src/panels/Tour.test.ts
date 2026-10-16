import { describe, expect, it } from "vitest";
import type { Venue } from "@/api/types";
import { buildShots } from "./Tour";

const sq = (x: number, y: number, s: number): [number, number][] => [[x, y], [x + s, y], [x + s, y + s], [x, y + s]];
const floor = (id: string, name: string, elev: number, people: number, groups: { kind: string; share: number }[] = []) => ({
  floor_id: id, name, elevation_m: elev, walkable: sq(0, 0, 30), obstacles: [],
  exits: id === "F0" ? [{ id: "E1", polygon: sq(10, 0, 2), width_m: 2 }] : [],
  zones: [{ id: `${id}z`, polygon: sq(2, 2, 10), people, groups }],
});

describe("the camera tour of a building", () => {
  it("says how the floors are joined and who is in the crowd", () => {
    const venue = {
      name: "Clinic", mode: "indoor",
      floors: [floor("F0", "Ground", 0, 40, [{ kind: "bed", share: 0.25 }]), floor("F1", "Ward floor", 3.5, 20)],
      stairs: [{ id: "s1", from_floor: "F1", to_floor: "F0", top_polygon: sq(20, 20, 2), bottom_polygon: sq(20, 14, 2), width_m: 1.2, length_m: 7 }],
    } as unknown as Venue;
    const captions = buildShots(venue, null, null).map((s) => s.caption);
    expect(captions[0]).toBe("Clinic. An indoor plan for 60 people, with 1 exit on 2 floors.");
    expect(captions).toContain("1 stair joins the floors; the narrowest is 1.2 metres wide. People per floor: Ground 40, Ward floor 20.");
    expect(captions).toContain("Among them: 10 patients in beds. They move at their own pace in the simulation.");
  });
  it("keeps the one-floor tour as it was", () => {
    const venue = { name: "Hall", mode: "indoor", floors: [floor("F0", "", 0, 100)], stairs: [] } as unknown as Venue;
    const captions = buildShots(venue, null, null).map((s) => s.caption);
    expect(captions[0]).toBe("Hall. An indoor plan for 100 people, with 1 exit.");
    expect(captions.some((c) => c.includes("stair"))).toBe(false);
  });
});
