import { describe, expect, it } from "vitest";
import type { RunResult, Venue } from "@/api/types";
import { openTarget, realCaseOf, simulatedPeak } from "./realCases";

const card = {
  id: "love_parade_2010",
  title: "Love Parade 2010 · Duisburg ramp",
  incident: "Love Parade crowd crush",
  date: "2010-07-24",
  place: "Duisburg, Germany",
  deaths: 21,
  toll: "21 people died and more than 500 were injured.",
  what_happened: "Arriving and leaving visitors met where the only ramp joined the tunnels.",
  lesson: "One route for both arrivals and departures turns a junction into a crush.",
  sources: [{ label: "Helbing & Mukerji (2012)", url: "https://doi.org/10.1140/epjds7" }, { label: "bad", url: "javascript:alert(1)" }],
  approximations: ["The ramp is drawn flat."],
};
const venue = (ext: Record<string, unknown> = { real_case: card }) => ({
  floors: [{ floor_id: "F0", zones: [{ id: "z1", label: "Arriving from the west", people: 10, polygon: [[0, 0], [60, 0], [60, 20], [0, 20]] }], exits: [], obstacles: [] }],
  extensions: ext,
} as unknown as Venue);
const run = (hotspots: Record<string, unknown>[], peak = 5.73) =>
  ({ metrics: { peak_density_ppm2: peak }, hotspots } as unknown as RunResult);
const label = (id: string) => ({ main_ramp_left1: "Narrow staircase" })[id] ?? id;

describe("real cases", () => {
  it("reads the case a venue was built from and keeps only web links as sources", () => {
    const c = realCaseOf(venue());
    expect(c?.title).toBe("Love Parade 2010 · Duisburg ramp");
    expect(c?.sources.map((s) => s.url)).toEqual(["https://doi.org/10.1140/epjds7"]);
    expect(realCaseOf(venue({}))).toBeNull();
    expect(realCaseOf(venue({ real_case: { id: "x" } }))).toBeNull();
    expect(realCaseOf(null)).toBeNull();
  });
  it("says where the simulated peak was: the exit it was near, else the zone it lies in", () => {
    expect(simulatedPeak(run([{ floor_id: "F0", x: 51.5, y: 24.5, peak_density_ppm2: 5.73, near: "main_ramp_left1" }]), venue(), label))
      .toEqual({ peak: 5.73, where: "Narrow staircase" });
    expect(simulatedPeak(run([{ floor_id: "F0", x: 45.5, y: 18.5, peak_density_ppm2: 4.9, near: null },
                              { floor_id: "F0", x: 99, y: 99, peak_density_ppm2: 3.1, near: null }], 4.9), venue(), label))
      .toEqual({ peak: 4.9, where: "Arriving from the west" });
    expect(simulatedPeak(run([{ floor_id: "F0", x: 99, y: 99, peak_density_ppm2: 3.1, near: null }], 3.1), venue(), label))
      .toEqual({ peak: 3.1, where: null });
    expect(simulatedPeak(run([], 0), venue(), label)).toBeNull();
    expect(simulatedPeak(null, venue(), label)).toBeNull();
  });
  it("opens a case where its next step is", () => {
    expect(openTarget({ project_id: "p1", session_id: "s1", status: "testing" })).toBe("/p/p1/work?session=s1&live=1");
    expect(openTarget({ project_id: "p1", session_id: "s1", status: "existing" })).toBe("/p/p1");
    expect(openTarget({ project_id: "p1", session_id: null, status: "needs_fixes" })).toBe("/p/p1/describe");
    expect(openTarget({ project_id: "p1", session_id: null, status: "existing" })).toBe("/p/p1/describe");
  });
});
