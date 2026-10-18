import { describe, expect, it } from "vitest";
import type { Venue } from "@/api/types";
import { floorsSummary, type TrajLike } from "./floors";

const sq = (x: number, y: number): [number, number][] => [[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1]];

/** frames of [id, x, y, floorIndex] */
function traj(frames: [number, number, number, number][][], floors = ["F0", "F1"]): TrajLike {
  return {
    index: { times: frames.map((_, k) => k * 10), floors, origin: [0, 0], scale: 1 },
    frameCount: frames.length,
    frame: (k) => {
      const f = frames[k];
      return { n: f.length, ids: Uint16Array.from(f.map((p) => p[0])), xs: Int16Array.from(f.map((p) => p[1])),
               ys: Int16Array.from(f.map((p) => p[2])), floors: Uint8Array.from(f.map((p) => p[3])) };
    },
  };
}

const venue = {
  floors: [{ floor_id: "F0" }, { floor_id: "F1" }],
  stairs: [
    { id: "west", from_floor: "F1", to_floor: "F0", top_polygon: sq(0, 0), bottom_polygon: sq(0, 0) },
    { id: "east", from_floor: "F1", to_floor: "F0", top_polygon: sq(50, 0), bottom_polygon: sq(50, 0) },
  ],
} as unknown as Venue;

describe("floors summary", () => {
  it("counts people per floor, when each floor clears, and who took which stair", () => {
    const s = floorsSummary(traj([
      [[1, 5, 0, 1], [2, 48, 0, 1], [3, 20, 0, 0]],
      [[1, 1, 0, 0], [2, 49, 0, 1]],
      [[1, 2, 0, 0], [2, 50, 0, 0]],
      [],
    ]), venue);
    expect(s.floors.map((f) => f.start)).toEqual([1, 2]);
    expect(s.floors[1].clearS).toBe(20);
    expect(s.floors[0].clearS).toBe(30);
    expect(s.stairs).toEqual({ west: 1, east: 1 });
    expect(s.floors[1].series).toEqual([2, 1, 0, 0]);
  });
});
