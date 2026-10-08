import { describe, expect, it } from "vitest";
import type { Venue } from "@/api/types";
import { textHumanizer } from "@/lib/venueText";

const venue = {
  floors: [{
    floor_id: "F0", exits: [{ id: "street_w", label: "Street west end" }, { id: "door_e1", label: "East door" }],
    obstacles: [], zones: [{ id: "alley", label: "Alley" }],
  }],
  stairs: [],
} as unknown as Venue;

describe("textHumanizer", () => {
  it("replaces machine ids with the names shown in 3D", () => {
    const h = textHumanizer(venue);
    expect(h("Counterflow at street_w exit; open door_e1.")).toBe("Counterflow at Street west end exit; open East door.");
  });

  it("leaves plain words that double as ids alone", () => {
    expect(textHumanizer(venue)("Sudden slowdown in alley zone")).toBe("Sudden slowdown in alley zone");
  });
});
