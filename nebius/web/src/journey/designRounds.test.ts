import { describe, expect, it } from "vitest";
import type { Venue } from "@/api/types";
import { designOf } from "./DesignRounds";

describe("design rounds", () => {
  it("reads the rounds and the site the designer stored on the venue", () => {
    const venue = { extensions: { generated: {
      design_rounds: [{ round: 1, summary: "7 storeys", problems: [], fixes: [], notes: [], critic: "ok", critique: [], evac_s: 120, not_out: 0, kept: true }],
      site: { source: "OpenStreetMap way 42", width_m: 22, depth_m: 14 },
    } } } as unknown as Venue;
    const d = designOf(venue);
    expect(d.rounds.map((r) => r.round)).toEqual([1]);
    expect(d.site?.source).toBe("OpenStreetMap way 42");
  });

  it("is empty for a venue that was not designed from words", () => {
    expect(designOf({ extensions: {} } as unknown as Venue)).toEqual({ rounds: [], site: null });
    expect(designOf(undefined).rounds).toEqual([]);
  });
});
