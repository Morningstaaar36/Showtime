import { describe, expect, it } from "vitest";
import { stoodInLine } from "./stoodIn";

describe("when rules stood in for the AI", () => {
  it("names each part the rules played, in plain words, and why", () => {
    expect(stoodInLine({ red_team: "The language model did not answer: 401", judge: "The language model did not answer: 401" }))
      .toEqual({
        text: "The AI didn't answer, so built-in rules wrote the red team scenarios and the summary. Every scenario was still simulated.",
        why: "The language model did not answer: 401",
      });
    expect(stoodInLine({ blue_team: "x" })?.text).toBe("The AI didn't answer, so built-in rules wrote the fixes. Every scenario was still simulated.");
  });
  it("says nothing when the AI answered (or for a test saved before this was recorded)", () => {
    expect(stoodInLine({})).toBeNull();
    expect(stoodInLine(undefined)).toBeNull();
  });
});
